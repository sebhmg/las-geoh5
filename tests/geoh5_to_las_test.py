#  Copyright (c) 2023 Mira Geoscience Ltd.
#
#  This file is part of my_app project.
#
#  All rights reserved.
#

import random
import string
from pathlib import Path

import lasio
import numpy as np
import pytest
from geoh5py.groups.drillhole_group import DrillholeGroup
from geoh5py.objects.drillhole import Drillhole
from geoh5py.shared.utils import compare_entities
from geoh5py.workspace import Workspace

from las_geoh5 import export_las, import_las, write_uijson
from las_geoh5.export_las import drillhole_to_las, write_curves
from las_geoh5.import_las import (
    create_or_append_drillhole,
    get_depths,
    las_to_drillhole,
)


def test_get_depths():
    lasfile = lasio.LASFile()
    lasfile.append_curve("DEPTH", np.arange(0, 10))
    assert np.all(get_depths(lasfile) == np.arange(0, 10))
    lasfile = lasio.LASFile()
    lasfile.append_curve("DEPT", np.arange(0, 10))
    assert np.all(get_depths(lasfile) == np.arange(0, 10))
    lasfile = lasio.LASFile()
    with pytest.raises(KeyError, match="curve named 'DEPTH' or 'DEPT'."):
        get_depths(lasfile)


def test_create_or_append_drillhole(tmp_path):
    with Workspace.create(Path(tmp_path / "test.geoh5")) as workspace:
        drillhole_group = DrillholeGroup.create(workspace, name="dh_group")

        # Create a workspace
        drillhole_a = Drillhole.create(
            workspace,
            collar=np.r_[0.0, 10.0, 10],
            parent=drillhole_group,
            name="dh1",
        )
        drillhole_a.add_data(
            {
                "my_data": {
                    "depth": np.arange(0, 50.0),
                    "values": np.random.randn(50),
                },
            }
        )
        write_curves(drillhole_a, tmp_path, directory=False)

        file = lasio.read(Path(tmp_path / "dh1.las"), mnemonic_case="preserve")
        assert "DEPTH" in [k.mnemonic for k in file.curves]
        file.append_curve("my_new_data", np.random.randn(50))
        drillhole = create_or_append_drillhole(workspace, file, drillhole_group)

        # New data is appended to existing drillhole
        assert drillhole.uid == drillhole_a.uid
        assert drillhole.get_data("my_new_data")

        file = lasio.read(Path(tmp_path / "dh1.las"), mnemonic_case="preserve")
        file.well["X"] = 10.0
        drillhole = create_or_append_drillhole(workspace, file, drillhole_group)

        # New data should be placed in a new drillhole object with augmented name
        assert drillhole.uid != drillhole_a.uid
        assert drillhole.name == "dh1 (1)"

        file.well["WELL"] = "dh2"
        drillhole = create_or_append_drillhole(workspace, file, drillhole_group)
        # Same data should be read into a new
        assert workspace.get_entity("dh2")


def test_add_survey(tmp_path):
    with Workspace.create(Path(tmp_path / "test.geoh5")) as workspace:
        drillhole_group = DrillholeGroup.create(workspace, name="dh_group")

        # Create a workspace
        drillhole_a = Drillhole.create(
            workspace,
            collar=np.r_[0.0, 10.0, 10],
            parent=drillhole_group,
            name="dh1",
        )
        surveys = np.c_[
            np.linspace(0, 100, 50),
            np.ones(50) * 45.0,
            np.linspace(-89, -75, 50),
        ]
        drillhole_a.surveys = surveys

        drillhole_a.add_data(
            {
                "my_data": {
                    "depth": np.arange(0, 50.0),
                    "values": np.random.randn(50),
                },
            }
        )
        drillhole_to_las(drillhole_a, tmp_path, directory=False)
        basepath = Path(tmp_path)
        data = lasio.read(Path(basepath / "dh1.las"))
        survey = Path(basepath / "dh1_survey.las")
        drillhole = las_to_drillhole(workspace, data, drillhole_group, survey=survey)
        assert np.allclose(drillhole.surveys, surveys)

        survey.unlink()
        survey = Path(basepath / "dh1_survey.csv")
        np.savetxt(survey, surveys, delimiter=",", header="depth, dip, azimuth")
        drillhole = las_to_drillhole(workspace, data, drillhole_group, survey=survey)
        assert np.allclose(drillhole.surveys, surveys)


def test_import_las(tmp_path):  # pylint: disable=too-many-locals
    n_data = 10
    with Workspace.create(Path(tmp_path / "test.geoh5")) as workspace:
        # Create a workspace
        dh_group = DrillholeGroup.create(workspace, name="dh_group")
        well_a = Drillhole.create(
            workspace,
            collar=np.r_[0.0, 10.0, 10],
            parent=dh_group,
            name="dh1",
        )

        surveys = np.c_[
            np.linspace(0, 100, n_data),
            np.ones(n_data) * 45.0,
            np.linspace(-89, -75, n_data),
        ]
        well_a.surveys = surveys

        # Add from-to data
        from_to_a = np.sort(np.random.uniform(low=0.05, high=100, size=(50,))).reshape(
            (-1, 2)
        )

        _ = well_a.add_data(
            {
                "interval_values": {
                    "values": np.random.randn(from_to_a.shape[0]),
                    "from-to": from_to_a.tolist(),
                },
            }
        )

        # Add depth data
        _ = well_a.add_data(
            {
                "depth_values": {
                    "depth": np.arange(0, 50.0),
                    "values": np.random.randn(50),
                },
                "collocated_depth_values": {
                    "depth": np.arange(0.01, 50.01),
                    "values": np.random.randn(50),
                },
            }
        )

        well_b = Drillhole.create(
            workspace,
            collar=np.r_[10.0, 10.0, 10],
            surveys=np.c_[
                np.linspace(0, 100, n_data),
                np.ones(n_data) * 45.0,
                np.linspace(-89, -75, n_data),
            ],
            parent=dh_group,
            name="dh2",
        )

        # Add from-to data
        n = 25  # pylint: disable=invalid-name
        from_to_a = np.sort(
            np.random.uniform(low=0.05, high=100, size=(2 * n,))
        ).reshape((-1, 2))

        randstrs = ["".join(random.sample(string.ascii_lowercase, 6)) for k in range(n)]
        _ = well_b.add_data(
            {
                "interval_values": {
                    "values": np.random.randn(from_to_a.shape[0]),
                    "from-to": from_to_a.tolist(),
                },
                "interval_referenced": {
                    "type": "referenced",
                    "values": np.arange(1, n + 1),
                    "value_map": dict(zip(np.arange(1, n + 1), randstrs)),
                    "from-to": from_to_a.tolist(),
                },
            }
        )

        export_las(dh_group, tmp_path, name="dh_group")
        dh_group2 = import_las(workspace, Path(tmp_path / "dh_group"), name="dh_group2")

        assert len(dh_group.children) == len(dh_group2.children)
        for child in dh_group.children:
            matches = [k for k in dh_group2.children if k.name == child.name]
            assert len(matches) == 1
            other_child = matches[0]
            compare_entities(
                child,
                other_child,
                ignore=["_uid", "_parent", "_property_groups"],
                decimal=4,
            )
            assert len(child.property_groups) == len(other_child.property_groups)
            for pg in child.property_groups:  # pylint: disable=invalid-name
                matches = [k for k in other_child.property_groups if k.name == pg.name]
                assert len(matches) == 1
                other_pg = matches[0]
                properties = [workspace.get_entity(k)[0] for k in pg.properties]
                other_properties = [
                    workspace.get_entity(k)[0] for k in other_pg.properties
                ]
                assert len(properties) == len(other_properties)
                for prop in properties:
                    matches = [k for k in other_properties if k.name == prop.name]
                    assert len(matches) == 1
                    other_prop = matches[0]
                    compare_entities(
                        prop,
                        other_prop,
                        ignore=["_uid", "_parent", "_property_groups"],
                        decimal=4,
                    )

        assert len(dh_group.property_group_ids) == len(dh_group2.property_group_ids)


def test_write_uijson(tmp_path):
    write_uijson(tmp_path)
