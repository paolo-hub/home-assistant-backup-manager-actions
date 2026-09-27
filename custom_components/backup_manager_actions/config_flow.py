"""Config flow for Backup Manager Actions."""

from __future__ import annotations

from typing import Any, override

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, NAME


class BackupManagerActionsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure Backup Manager Actions."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle setup from the UI."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
