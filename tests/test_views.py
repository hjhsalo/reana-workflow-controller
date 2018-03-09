# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# REANA is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# REANA; if not, write to the Free Software Foundation, Inc., 59 Temple Place,
# Suite 330, Boston, MA 02111-1307, USA.
#
# In applying this license, CERN does not waive the privileges and immunities
# granted to it by virtue of its status as an Intergovernmental Organization or
# submit itself to any jurisdiction.
"""REANA-Workflow-Controller module tests."""

import io
import json
import os
import uuid

import fs
import pytest
from flask import url_for
from werkzeug.utils import secure_filename

from reana_workflow_controller.config import (ALLOWED_LIST_DIRECTORIES,
                                              ALLOWED_SEED_DIRECTORIES)
from reana_workflow_controller.models import Workflow, WorkflowStatus
from reana_workflow_controller.rest import START, STOP
from reana_workflow_controller.utils import (get_analysis_files_dir,
                                             get_user_analyses_dir)

status_dict = {
    START: WorkflowStatus.running,
    STOP: WorkflowStatus.finished
}


def test_get_workflows(app, default_user, db_session, cwl_workflow_with_name):
    """Test listing all workflows."""
    with app.test_client() as client:
        workflow_uuid = uuid.uuid4()
        workflow_name = 'my_test_workflow'
        workflow = Workflow(
            id_=workflow_uuid,
            name=workflow_name,
            workspace_path='',
            status=WorkflowStatus.finished,
            owner_id=default_user.id_,
            specification=cwl_workflow_with_name['specification'],
            parameters=cwl_workflow_with_name['parameters'],
            type_=cwl_workflow_with_name['type'])
        db_session.add(workflow)
        db_session.commit()

        res = client.get(url_for('api.get_workflows'),
                         query_string={
                             "user": default_user.id_,
                             "organization": 'default'})
        assert res.status_code == 200
        response_data = json.loads(res.get_data(as_text=True))
        expected_data = [
            {
                "id": str(workflow.id_),
                "name": workflow.name + '.1',  # Add run_number
                "organization": "default",
                "status": workflow.status.name,
                "user": str(workflow.owner_id)
            }
        ]

        assert response_data == expected_data


def test_get_workflows_wrong_user(app):
    """Test list of workflows for unknown user."""
    with app.test_client() as client:
        random_user_uuid = uuid.uuid4()
        res = client.get(url_for('api.get_workflows'),
                         query_string={
                             "user": random_user_uuid,
                             "organization": 'default'})
        assert res.status_code == 404


def test_get_workflows_missing_user(app):
    """Test listing all workflows with missing user."""
    with app.test_client() as client:
        res = client.get(url_for('api.get_workflows'),
                         query_string={"organization": 'default'})
        assert res.status_code == 400


def test_get_workflows_wrong_organization(app, default_user):
    """Test list of workflows for unknown organization."""
    with app.test_client() as client:
        organization = 'wrong_organization'
        res = client.get(url_for('api.get_workflows'),
                         query_string={
                             "user": default_user.id_,
                             "organization": organization})
        assert res.status_code == 404


def test_get_workflows_missing_organization(app, default_user):
    """Test listing all workflows with missing organization."""
    with app.test_client() as client:
        res = client.get(url_for('api.get_workflows'),
                         query_string={"user": default_user.id_})
        assert res.status_code == 400


def test_create_workflow_with_name(app, default_user, tmp_shared_volume_path,
                                   cwl_workflow_with_name):
    """Test create workflow and its workspace by specifying a name."""
    with app.test_client() as client:
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_with_name))

        assert res.status_code == 201
        response_data = json.loads(res.get_data(as_text=True))

        # Check workflow fetch by id
        workflow_by_id = Workflow.query.filter(
            Workflow.id_ == response_data.get('workflow_id')).first()
        assert workflow_by_id

        # Check workflow fetch by name and that name of created workflow
        # is the same that was supplied to `api.create_workflow`
        workflow_by_name = Workflow.query.filter(
            Workflow.name == 'my_test_workflow').first()
        assert workflow_by_name

        workflow = workflow_by_id

        workflow.specification == cwl_workflow_with_name['specification']
        workflow.parameters == cwl_workflow_with_name['parameters']
        workflow.type_ == cwl_workflow_with_name['type']

        # Check that workflow workspace exist
        user_analyses_workspace = get_user_analyses_dir(
            organization, str(default_user.id_))
        workflow_workspace = os.path.join(
            tmp_shared_volume_path,
            user_analyses_workspace,
            str(workflow.id_))
        assert os.path.exists(workflow_workspace)


def test_create_workflow_without_name(app, default_user,
                                      tmp_shared_volume_path,
                                      cwl_workflow_without_name):
    """Test create workflow and its workspace without specifying a name."""
    with app.test_client() as client:

        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_without_name))

        assert res.status_code == 201
        response_data = json.loads(res.get_data(as_text=True))

        # Check workflow fetch by id
        workflow_by_id = Workflow.query.filter(
            Workflow.id_ == response_data.get('workflow_id')).first()
        assert workflow_by_id

        # Check workflow fetch by name and that name of created workflow
        # is the same that was supplied to `api.create_workflow`

        import reana_workflow_controller
        default_workflow_name = reana_workflow_controller.config.\
            DEFAULT_NAME_FOR_WORKFLOWS

        workflow_by_name = Workflow.query.filter(
            Workflow.name == default_workflow_name).first()
        assert workflow_by_name

        workflow = workflow_by_id

        workflow.specification == cwl_workflow_without_name['specification']
        workflow.parameters == cwl_workflow_without_name['parameters']
        workflow.type_ == cwl_workflow_without_name['type']

        # Check that workflow workspace exist
        user_analyses_workspace = get_user_analyses_dir(
            organization, str(default_user.id_))
        workflow_workspace = os.path.join(
            tmp_shared_volume_path,
            user_analyses_workspace,
            str(workflow.id_))
        assert os.path.exists(workflow_workspace)


def test_create_workflow_wrong_user(app, tmp_shared_volume_path,
                                    cwl_workflow_with_name):
    """Test create workflow providing unknown user."""
    with app.test_client() as client:
        organization = 'default'
        random_user_uuid = uuid.uuid4()
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": random_user_uuid,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_with_name))

        assert res.status_code == 404
        response_data = json.loads(res.get_data(as_text=True))
        workflow = Workflow.query.filter(
            Workflow.id_ == response_data.get('workflow_id')).first()
        # workflow exist in DB
        assert not workflow
        # workflow workspace exist
        user_analyses_workspace = get_user_analyses_dir(
            organization, str(random_user_uuid))
        workflow_workspace = os.path.join(
            tmp_shared_volume_path,
            user_analyses_workspace)
        assert not os.path.exists(workflow_workspace)


def test_get_workflow_outputs_absent_file(app, default_user,
                                          cwl_workflow_with_name):
    """Test download output file."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_with_name))

        assert res.status_code == 201
        response_data = json.loads(res.get_data(as_text=True))
        workflow_uuid = response_data.get('workflow_id')
        file_name = 'input.csv'
        res = client.get(
            url_for('api.get_workflow_outputs_file',
                    workflow_id_or_name=workflow_uuid,
                    file_name=file_name),
            query_string={"user": default_user.id_,
                          "organization": organization},
            content_type='application/json',
            data=json.dumps(cwl_workflow_with_name))

        assert res.status_code == 404
        response_data = json.loads(res.get_data(as_text=True))
        assert response_data == {'message': 'input.csv does not exist.'}


def test_get_workflow_outputs_file(app, default_user, cwl_workflow_with_name):
    """Test download output file."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_with_name))

        response_data = json.loads(res.get_data(as_text=True))
        workflow_uuid = response_data.get('workflow_id')
        workflow = Workflow.query.filter(
            Workflow.id_ == workflow_uuid).first()
        # create file
        file_name = 'output name.csv'
        file_binary_content = b'1,2,3,4\n5,6,7,8'
        outputs_directory = get_analysis_files_dir(workflow, 'output')
        # write file in the workflow workspace under `outputs` directory:
        # we use `secure_filename` here because
        # we use it in server side when adding
        # files
        file_path = os.path.join(outputs_directory, file_name)
        # because outputs directory doesn't exist by default
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'wb+') as f:
            f.write(file_binary_content)
        res = client.get(
            url_for('api.get_workflow_outputs_file',
                    workflow_id_or_name=workflow_uuid,
                    file_name=file_name),
            query_string={"user": default_user.id_,
                          "organization": organization},
            content_type='application/json',
            data=json.dumps(cwl_workflow_with_name))
        assert res.data == file_binary_content


def test_get_workflow_outputs_file_with_path(app, default_user,
                                             cwl_workflow_with_name):
    """Test download output file prepended with path."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_with_name))

        response_data = json.loads(res.get_data(as_text=True))
        workflow_uuid = response_data.get('workflow_id')
        workflow = Workflow.query.filter(
            Workflow.id_ == workflow_uuid).first()
        # create file
        file_name = 'first/1991/output.csv'
        file_binary_content = b'1,2,3,4\n5,6,7,8'
        outputs_directory = get_analysis_files_dir(workflow, 'output')
        # write file in the workflow workspace under `outputs` directory:
        # we use `secure_filename` here because
        # we use it in server side when adding
        # files
        file_path = os.path.join(outputs_directory, file_name)
        # because outputs directory doesn't exist by default
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'wb+') as f:
            f.write(file_binary_content)
        res = client.get(
            url_for('api.get_workflow_outputs_file',
                    workflow_id_or_name=workflow_uuid,
                    file_name=file_name),
            query_string={"user": default_user.id_,
                          "organization": organization},
            content_type='application/json',
            data=json.dumps(cwl_workflow_with_name))
        assert res.data == file_binary_content


@pytest.mark.parametrize("file_type", ALLOWED_LIST_DIRECTORIES.keys())
def test_get_workflow_files(app, default_user, tmp_shared_volume_path,
                            file_type, cwl_workflow_with_name):
    """Test get list of input files."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_with_name))

        response_data = json.loads(res.get_data(as_text=True))
        workflow_uuid = response_data.get('workflow_id')
        workflow = Workflow.query.filter(
            Workflow.id_ == workflow_uuid).first()
        # create file
        absolute_path_workflow_workspace = \
            os.path.join(tmp_shared_volume_path,
                         workflow.workspace_path)
        fs_ = fs.open_fs(absolute_path_workflow_workspace)
        # from config
        inputs_relative_path = \
            app.config['ALLOWED_LIST_DIRECTORIES'][file_type]
        test_files = []
        for i in range(5):
            file_name = '{0}.csv'.format(i)
            subdir_name = str(uuid.uuid4())
            subdir = fs.path.join(inputs_relative_path, subdir_name)
            fs_.makedirs(subdir)
            fs_.touch('{0}/{1}'.format(subdir, file_name))
            test_files.append(os.path.join(subdir_name, file_name))

        res = client.get(
            url_for('api.get_workflow_files',
                    workflow_id_or_name=workflow_uuid),
            query_string={"user": default_user.id_,
                          "organization": organization,
                          "file_type": file_type},
            content_type='application/json',
            data=json.dumps(cwl_workflow_with_name))
        for file_ in json.loads(res.data.decode()):
            assert file_.get('name') in test_files


@pytest.mark.parametrize("file_type", ALLOWED_LIST_DIRECTORIES.keys())
def test_get_unknown_workflow_files(app, default_user, file_type):
    """Test get list of input files for non existing workflow."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        random_workflow_uuid = str(uuid.uuid4())

        res = client.get(
            url_for('api.get_workflow_files',
                    workflow_id_or_name=random_workflow_uuid),
            query_string={"user": default_user.id_,
                          "organization": organization,
                          "file_type": file_type},
            content_type='application/json')

        assert res.status_code == 404
        response_data = json.loads(res.get_data(as_text=True))
        expected_data = {'message': 'Workflow {0} does not exist.'.
                         format(random_workflow_uuid)}
        assert response_data == expected_data


def test_get_workflow_status_with_uuid(app, db_session, default_user,
                                       cwl_workflow_with_name):
    """Test get workflow status."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_with_name))

        response_data = json.loads(res.get_data(as_text=True))
        workflow_uuid = response_data.get('workflow_id')
        workflow = Workflow.query.filter(
            Workflow.id_ == workflow_uuid).first()

        res = client.get(url_for('api.get_workflow_status',
                                 workflow_id_or_name=workflow_uuid),
                         query_string={
                             "user": default_user.id_,
                             "organization": organization},
                         content_type='application/json',
                         data=json.dumps(cwl_workflow_with_name))
        json_response = json.loads(res.data.decode())
        assert json_response.get('status') == workflow.status.name
        workflow.status = WorkflowStatus.finished
        db_session.commit()

        res = client.get(url_for('api.get_workflow_status',
                                 workflow_id_or_name=workflow_uuid),
                         query_string={
                             "user": default_user.id_,
                             "organization": organization},
                         content_type='application/json',
                         data=json.dumps(cwl_workflow_with_name))
        json_response = json.loads(res.data.decode())
        assert json_response.get('status') == workflow.status.name


def test_get_workflow_status_with_name(app, db_session, default_user,
                                       cwl_workflow_with_name):
    """Test get workflow status."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        # res = client.post(url_for('api.create_workflow'),
        #                   query_string={
        #                       "user": default_user.id_,
        #                       "organization": organization},
        #                   content_type='application/json',
        #                   data=json.dumps(cwl_workflow_with_name))
        #
        # response_data = json.loads(res.get_data(as_text=True))
        # workflow_name = response_data.get('workflow_name')

        workflow_uuid = uuid.uuid4()
        workflow_name = 'my_test_workflow'
        workflow = Workflow(
            id_=workflow_uuid,
            name=workflow_name,
            workspace_path='',
            status=WorkflowStatus.finished,
            owner_id=default_user.id_,
            specification=cwl_workflow_with_name['specification'],
            parameters=cwl_workflow_with_name['parameters'],
            type_=cwl_workflow_with_name['type'])
        db_session.add(workflow)
        db_session.commit()

        workflow = Workflow.query.filter(
            Workflow.name == workflow_name).first()

        res = client.get(url_for('api.get_workflow_status',
                                 workflow_id_or_name=workflow_name + '.1'),
                         query_string={
                             "user": default_user.id_,
                             "organization": organization},
                         content_type='application/json',
                         data=json.dumps(cwl_workflow_with_name))
        json_response = json.loads(res.data.decode())

        assert json_response.get('status') == workflow.status.name
        workflow.status = WorkflowStatus.finished
        db_session.commit()

        res = client.get(url_for('api.get_workflow_status',
                                 workflow_id_or_name=workflow_name + '.1'),
                         query_string={
                             "user": default_user.id_,
                             "organization": organization},
                         content_type='application/json',
                         data=json.dumps(cwl_workflow_with_name))
        json_response = json.loads(res.data.decode())
        assert json_response.get('status') == workflow.status.name


def test_get_workflow_status_unauthorized(app, default_user,
                                          cwl_workflow_with_name):
    """Test get workflow status unauthorized."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_with_name))

        response_data = json.loads(res.get_data(as_text=True))
        workflow_created_uuid = response_data.get('workflow_id')
        random_user_uuid = uuid.uuid4()
        res = client.get(url_for('api.get_workflow_status',
                                 workflow_id_or_name=workflow_created_uuid),
                         query_string={
                             "user": random_user_uuid,
                             "organization": organization},
                         content_type='application/json',
                         data=json.dumps(cwl_workflow_with_name))
        assert res.status_code == 403


def test_get_workflow_status_unknown_workflow(app, default_user,
                                              cwl_workflow_with_name):
    """Test get workflow status for unknown workflow."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_with_name))
        random_workflow_uuid = uuid.uuid4()
        res = client.get(url_for('api.get_workflow_status',
                                 workflow_id_or_name=random_workflow_uuid),
                         query_string={
                             "user": default_user.id_,
                             "organization": organization},
                         content_type='application/json',
                         data=json.dumps(cwl_workflow_with_name))
        assert res.status_code == 404


def test_set_workflow_status(app, default_user, yadage_workflow_with_name):
    """Test set workflow status "Start"."""
    with app.test_client() as client:
        os.environ["TESTS"] = "True"
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(yadage_workflow_with_name))

        response_data = json.loads(res.get_data(as_text=True))
        workflow_created_uuid = response_data.get('workflow_id')
        workflow = Workflow.query.filter(
            Workflow.id_ == workflow_created_uuid).first()
        assert workflow.status == WorkflowStatus.created
        payload = START
        res = client.put(url_for('api.set_workflow_status',
                                 workflow_id_or_name=workflow_created_uuid),
                         query_string={
                             "user": default_user.id_,
                             "organization": organization},
                         content_type='application/json',
                         data=json.dumps(payload))
        json_response = json.loads(res.data.decode())
        assert json_response.get('status') == status_dict[payload].name


def test_start_already_started_workflow(app, db_session, default_user):
    """Test start workflow twice."""
    with app.test_client() as client:
        os.environ["TESTS"] = "True"
        # create workflow
        organization = 'default'
        data = {'parameters': {'input': 'job.json'},
                'specification': {'first': 'do this',
                                  'second': 'do that'},
                'type': 'yadage'}
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(data))

        response_data = json.loads(res.get_data(as_text=True))
        workflow_created_uuid = response_data.get('workflow_id')
        workflow = Workflow.query.filter(
            Workflow.id_ == workflow_created_uuid).first()
        assert workflow.status == WorkflowStatus.created
        payload = START
        res = client.put(url_for('api.set_workflow_status',
                                 workflow_id_or_name=workflow_created_uuid),
                         query_string={
                             "user": default_user.id_,
                             "organization": organization},
                         content_type='application/json',
                         data=json.dumps(payload))
        json_response = json.loads(res.data.decode())
        assert json_response.get('status') == status_dict[payload].name
        res = client.put(url_for('api.set_workflow_status',
                                 workflow_id_or_name=workflow_created_uuid),
                         query_string={
                             "user": default_user.id_,
                             "organization": organization},
                         content_type='application/json',
                         data=json.dumps(payload))
        json_response = json.loads(res.data.decode())
        assert res.status_code == 409
        expected_message = ("Workflow {0} could not be started because it is"
                            " already running.").format(workflow_created_uuid)
        assert json_response.get('message') == expected_message


def test_set_workflow_status_unauthorized(app, default_user,
                                          yadage_workflow_with_name):
    """Test set workflow status unauthorized."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(yadage_workflow_with_name))

        response_data = json.loads(res.get_data(as_text=True))
        workflow_created_uuid = response_data.get('workflow_id')
        random_user_uuid = uuid.uuid4()
        payload = START
        res = client.put(url_for('api.set_workflow_status',
                                 workflow_id_or_name=workflow_created_uuid),
                         query_string={
                             "user": random_user_uuid,
                             "organization": organization},
                         content_type='application/json',
                         data=json.dumps(payload))
        assert res.status_code == 403


def test_set_workflow_status_unknown_workflow(app, default_user,
                                              yadage_workflow_with_name):
    """Test set workflow status for unknown workflow."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(yadage_workflow_with_name))
        random_workflow_uuid = uuid.uuid4()
        payload = START
        res = client.put(url_for('api.set_workflow_status',
                                 workflow_id_or_name=random_workflow_uuid),
                         query_string={
                             "user": default_user.id_,
                             "organization": organization},
                         content_type='application/json',
                         data=json.dumps(payload))
        assert res.status_code == 404


@pytest.mark.parametrize("file_type", ALLOWED_SEED_DIRECTORIES.keys())
def test_seed_workflow_workspace(app, db_session, default_user, file_type,
                                 cwl_workflow_with_name):
    """Test download output file."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_with_name))

        response_data = json.loads(res.get_data(as_text=True))
        workflow_uuid = response_data.get('workflow_id')
        workflow = Workflow.query.filter(
            Workflow.id_ == workflow_uuid).first()
        # create file
        file_name = 'dataset.csv'
        file_binary_content = b'1,2,3,4\n5,6,7,8'

        res = client.post(
            url_for('api.seed_workflow_workspace',
                    workflow_id_or_name=workflow_uuid),
            query_string={"user": default_user.id_,
                          "organization": organization,
                          "file_name": file_name,
                          "file_type": file_type},
            content_type='multipart/form-data',
            data={'file_content': (io.BytesIO(file_binary_content),
                                   file_name)})
        assert res.status_code == 200
        # remove workspace directory from path
        files_directory = get_analysis_files_dir(workflow, file_type, 'seed')

        # we use `secure_filename` here because
        # we use it in server side when adding
        # files
        file_path = os.path.join(files_directory, secure_filename(file_name))

        with open(file_path, 'rb') as f:
            assert f.read() == file_binary_content


def test_seed_unknown_workflow_workspace(app, default_user):
    """Test download output file."""
    with app.test_client() as client:
        random_workflow_uuid = uuid.uuid4()
        # create file
        file_name = 'dataset.csv'
        file_binary_content = b'1,2,3,4\n5,6,7,8'

        res = client.post(
            url_for('api.seed_workflow_workspace',
                    workflow_id_or_name=random_workflow_uuid),
            query_string={"user": default_user.id_,
                          "organization": "default",
                          "file_name": file_name},
            content_type='multipart/form-data',
            data={'file_content': (io.BytesIO(file_binary_content),
                                   file_name)})
        assert res.status_code == 404


def test_seed_workflow_workspace_with_wrong_file_type(app, default_user,
                                                      cwl_workflow_with_name):
    """Seed files with wrong input type."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_with_name))

        response_data = json.loads(res.get_data(as_text=True))
        workflow_uuid = response_data.get('workflow_id')

        # create file
        file_name = 'helloworld.py'
        file_binary_content = b'print("Hello world.")\n'

        res = client.post(
            url_for('api.seed_workflow_workspace',
                    workflow_id_or_name=workflow_uuid),
            query_string={"user": default_user.id_,
                          "organization": organization,
                          "file_name": file_name,
                          "file_type": "wrong-type"},
            content_type='multipart/form-data',
            data={'file_content': (io.BytesIO(file_binary_content),
                                   file_name)})
        assert res.status_code == 400


def test_get_created_workflow_logs(app, default_user, cwl_workflow_with_name):
    """Test get workflow logs."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(cwl_workflow_with_name))
        response_data = json.loads(res.get_data(as_text=True))
        workflow_uuid = response_data.get('workflow_id')
        workflow_name = response_data.get('workflow_name')
        res = client.get(url_for('api.get_workflow_logs',
                                 workflow_id_or_name=workflow_uuid),
                         query_string={
                             "user": default_user.id_,
                             "organization": organization},
                         content_type='application/json')
        assert res.status_code == 200
        response_data = json.loads(res.get_data(as_text=True))
        create_workflow_logs = ""
        expected_data = {
            'workflow_id': workflow_uuid,
            'workflow_name': workflow_name,
            'organization': organization,
            'user': str(default_user.id_),
            'logs': create_workflow_logs
        }
        assert response_data == expected_data


def test_get_unknown_workflow_logs(app, default_user,
                                   yadage_workflow_with_name):
    """Test set workflow status for unknown workflow."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(yadage_workflow_with_name))
        random_workflow_uuid = uuid.uuid4()
        res = client.get(url_for('api.get_workflow_logs',
                                 workflow_id_or_name=random_workflow_uuid),
                         query_string={
                             "user": default_user.id_,
                             "organization": organization},
                         content_type='application/json')
        assert res.status_code == 404


def test_get_workflow_logs_unauthorized(app, default_user,
                                        yadage_workflow_with_name):
    """Test set workflow status for unknown workflow."""
    with app.test_client() as client:
        # create workflow
        organization = 'default'
        res = client.post(url_for('api.create_workflow'),
                          query_string={
                              "user": default_user.id_,
                              "organization": organization},
                          content_type='application/json',
                          data=json.dumps(yadage_workflow_with_name))
        response_data = json.loads(res.get_data(as_text=True))
        workflow_uuid = response_data.get('workflow_id')
        random_user_uuid = uuid.uuid4()
        res = client.get(url_for('api.get_workflow_logs',
                                 workflow_id_or_name=workflow_uuid),
                         query_string={
                             "user": random_user_uuid,
                             "organization": organization},
                         content_type='application/json')
        assert res.status_code == 403
