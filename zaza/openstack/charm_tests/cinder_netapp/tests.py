#!/usr/bin/env python3

# Copyright 2021 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Encapsulate cinder-netapp testing."""

from zaza.openstack.charm_tests.cinder_backend.tests import CinderBackendTest


class CinderNetAppTest(CinderBackendTest):
    """Encapsulate netapp tests."""

    @classmethod
    def setUpClass(cls):
        """Run class setup for running tests."""
        super(CinderNetAppTest, cls).setUpClass()
        cls.keystone_session = openstack_utils.get_overcloud_keystone_session()
        cls.model_name = zaza.model.get_juju_model()
        cls.cinder_client = openstack_utils.get_cinder_session_client(
            cls.keystone_session)
        cls.zaza_volumes = []

    @classmethod
    def tearDown(cls):
        """Remove test resources."""
        for volume in cls.zaza_volumes:
            try:
                volume.detach()
                volume.force_delete()
            except Exception:
                pass

    def test_cinder_config(self):
        """Test that configuration options match our expectations."""
        expected_contents = {
            'cinder-netapp': {
                'netapp_storage_family': ['ontap_cluster'],
                'netapp_storage_protocol': ['iscsi'],
                'volume_driver':
                    ['cinder.volume.drivers.netapp.common.NetAppDriver'],
            }}

        zaza.model.run_on_leader(
            'cinder',
            'sudo cp /etc/cinder/cinder.conf /tmp/')
        zaza.model.block_until_oslo_config_entries_match(
            'cinder',
            '/tmp/cinder.conf',
            expected_contents,
            timeout=2)

    def _create_volumes(self, n):
        """Create N volumes."""
        volumes = []
        for _ in range(n):
            name = "zaza{}".format(uuid.uuid1().fields[0])
            vol = self.cinder_client.volumes.create(
                name=name,
                size='1')
            vol.reset_state('available')
            volumes.append(vol)
        self.zaza_volumes.extend(volumes)
        return volumes

    def _volume_host(self, vol):
        ret = getattr(vol, 'os-vol-host-attr:host', None)
        if ret is not None:
            return ret
        # A bit more roundabout, but also works when the attribute
        # hasn't been set yet, for whatever reason.
        for service in vol.manager.api.services.list():
            if 'cinder-volume' in service.binary:
                return service.host

    def test_create_volume(self):
        """Test creating volumes with basic configuration."""
        for vol in self._create_volumes(2):
            self.assertIsNotNone(vol)
            openstack_utils.resource_reaches_status(
                self.cinder_client.volumes,
                vol.id,
                wait_iteration_max_time=12000,
                stop_after_attempt=5,
                expected_status='available',
                msg='Volume status wait')
            test_vol = self.cinder_client.volumes.find(name=vol.name)
            host = self._volume_host(test_vol)
            self.assertIn('cinder-netapp', host)
