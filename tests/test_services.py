"""Exercise real service schemas and handlers with small HA boundary stubs."""
from __future__ import annotations

import asyncio
import importlib
import sys
import types

import voluptuous as vol
import test_adapter as fixture

core = sys.modules['homeassistant.core']
core.ServiceCall = object
core.ServiceResponse = dict
core.SupportsResponse = types.SimpleNamespace(OPTIONAL='optional', ONLY='only')
core.callback = lambda fn: fn
const = types.ModuleType('homeassistant.const')
const.Platform = types.SimpleNamespace(SENSOR='sensor', BINARY_SENSOR='binary_sensor')
sys.modules['homeassistant.const'] = const
helpers = types.ModuleType('homeassistant.helpers')
cv = types.ModuleType('homeassistant.helpers.config_validation')
cv.ensure_list = lambda value: value if isinstance(value, list) else [value]
cv.string = lambda value: str(value)
cv.boolean = bool
helpers.config_validation = cv
sys.modules['homeassistant.helpers'] = helpers
sys.modules['homeassistant.helpers.config_validation'] = cv
service = types.ModuleType('homeassistant.helpers.service')


def register(hass, domain, name, handler, **kwargs):
    """Capture registrations; authorization enforcement belongs to HA."""
    hass.handlers[name] = handler
    hass.schemas[name] = kwargs.get('schema', lambda value: value)


service.async_register_admin_service = register
sys.modules['homeassistant.helpers.service'] = service
coordinator_module = types.ModuleType('custom_components.backup_manager_actions.coordinator')
coordinator_module.BackupManagerActionsCoordinator = object
sys.modules[coordinator_module.__name__] = coordinator_module
services = importlib.import_module('custom_components.backup_manager_actions.services')
events = importlib.import_module('custom_components.backup_manager_actions.events')


class Coordinator:
    """Model the difference between queued and completed refreshes."""
    def __init__(self, hass, tracker):
        self.hass = hass
        self.tracker = tracker
        self.refreshed = False
        self.requested = False

    async def async_request_refresh(self):
        self.requested = True

    async def async_refresh(self):
        await asyncio.sleep(0)
        self.refreshed = True

    def async_publish_verified_bma_create(self, result):
        assert self.refreshed, 'Verified event preceded the completed refresh'
        data = self.tracker.record_verified_bma_create(result)
        if data is not None:
            self.hass.bus.async_fire(services.EVENT_BACKUP_CREATED, data)


def environment():
    manager = fixture.Manager()
    hass = fixture.Hass(manager)
    hass.handlers = {}
    hass.schemas = {}
    hass.events = []
    hass.bus = types.SimpleNamespace(async_fire=lambda name, data: hass.events.append((name, data)))
    tracker = events.BackupCreatedEventTracker()
    coordinator = Coordinator(hass, tracker)
    hass.data = {services.DOMAIN: {services.DATA_COORDINATORS: {coordinator}}}
    adapter = fixture.BackupManagerActionsAdapter(hass)
    services.async_setup_services(hass, adapter, tracker)
    return hass, adapter, coordinator


async def call(hass, name, data, return_response=True):
    return await hass.handlers[name](types.SimpleNamespace(
        data=hass.schemas[name](data), return_response=return_response))


def test_job_id_must_be_a_string():
    for schema, data in ((services.CREATE_SCHEMA, {'agent_ids': ['local']}),
                         (services.RETENTION_SCHEMA, {'source_type': 'bma', 'keep_last': 1})):
        for value in (123, True, None):
            try:
                schema({**data, 'job_id': value})
            except vol.Invalid:
                pass
            else:
                raise AssertionError(f'Non-string job_id accepted: {value!r}')


async def test_create_refreshes_before_emitting_one_event():
    hass, adapter, coordinator = environment()
    result = await call(hass, 'create', {'agent_ids': ['local', 'cloud'], 'job_id': 'full'})
    assert result['job_id'] == 'full'
    assert coordinator.refreshed
    assert len(hass.events) == 1
    assert hass.events[0][1]['backup_id'] == result['backup_id']


async def test_failed_create_refreshes_without_success_event():
    hass, adapter, coordinator = environment()
    hass.manager.create_agents = ['local']
    try:
        await call(hass, 'create', {'agent_ids': ['local', 'cloud']})
    except fixture.BackupManagerActionsError:
        pass
    else:
        raise AssertionError('Partial create should fail')
    assert coordinator.refreshed
    assert hass.events == []


async def test_failed_mutations_refresh_diagnostics():
    for name in ('delete', 'apply_retention'):
        hass, adapter, coordinator = environment()

        async def failing(**kwargs):
            raise fixture.BackupManagerActionsError('partial deletion')

        setattr(adapter, 'async_' + name, failing)
        data = {'backup_id': 'id'} if name == 'delete' else {'source_type': 'bma', 'job_id': 'full', 'keep_last': 1}
        try:
            await call(hass, name, data)
        except fixture.BackupManagerActionsError as err:
            assert str(err) == 'partial deletion'
        else:
            raise AssertionError('Mutation error swallowed')
        assert coordinator.refreshed


async def test_invalid_retention_schema_never_calls_adapter():
    hass, adapter, coordinator = environment()
    for value in (True, -1, 1.5, '1.5'):
        try:
            await call(hass, 'apply_retention', {'source_type': 'bma', 'job_id': 'full', 'keep_last': value})
        except vol.Invalid:
            pass
        else:
            raise AssertionError(f'Invalid counter accepted: {value!r}')
    assert not coordinator.refreshed


async def main():
    test_job_id_must_be_a_string()
    await test_create_refreshes_before_emitting_one_event()
    await test_failed_create_refreshes_without_success_event()
    await test_failed_mutations_refresh_diagnostics()
    await test_invalid_retention_schema_never_calls_adapter()
    print('service handler/schema simulation: OK')


if __name__ == '__main__':
    asyncio.run(main())
