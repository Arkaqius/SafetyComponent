"""
Notification Manager Module for Home Assistant Safety System

This module contains the NotificationManager class, designed to handle various types of notifications within a Home Assistant-based safety system. It facilitates the delivery of notifications through Home Assistant's notification services, dashboard updates, and other notification mechanisms such as lights and alarms. The NotificationManager is configurable, allowing for dynamic notification behaviors based on the severity of detected faults and system states.

The NotificationManager class provides a structured way to manage and execute notifications based on predefined levels of urgency. It maps different notification levels to specific methods that handle the logic for each notification type, ensuring that users are informed of system states and faults in a timely and appropriate manner.

Features include:

Configurable notification levels, allowing for tailored responses to different fault conditions.
Integration with Home Assistant services for sending notifications to devices, updating dashboard states, and controlling home automation entities like lights and alarms.
Support for additional information in notifications, enabling detailed fault descriptions to be communicated to the user.
Use of a unique faulttag to manage notifications effectively, ensuring that notifications related to the same fault instance can be tracked and correlated properly.
The faulttag feature is utilized to uniquely identify notifications associated with specific fault instances, facilitating efficient management of notification lifecycles, such as setting, updating, and clearing notifications. This ensures that users receive coherent and timely information regarding the status of faults.

This module plays a crucial role in the safety system's ability to notify users of faults and system states, contributing to the overall responsiveness and reliability of the system.

Classes:

    NotificationManager: Manages the configuration and execution of notifications within the safety system.
"""
from typing import Optional, Callable
import appdaemon.plugins.hass.hassapi as hass  # type: ignore
from shared.types_common import FaultState


class NotificationManager:
    """
    A manager for sending notifications within a Home Assistant-based safety system, using various
    methods like alerts to mobile devices, dashboard updates, and control of home automation entities
    (e.g., lights, alarms) based on event severity.

    Attributes:
        hass_app (hass.Hass): An instance of the Home Assistant application for service calls.
        notification_config (dict): Configuration for notification preferences, including entity IDs.

    Args:
        hass_app (hass.Hass): The Home Assistant application instance.
        notification_config (dict): Configuration for different notification levels and entities.
    """

    def __init__(self, hass_app: hass.Hass, notification_config: dict):
        """
        Initializes the NotificationManager with Home Assistant and notification configurations.

        Parameters:
            hass_app: Home Assistant application instance for making service calls.
            notification_config: Configurations for notification levels and corresponding entities.
        """
        self.hass_app = hass_app
        self.notification_config = notification_config
        self.active_notification: dict[str, dict] = {}

        # Map notification levels to their respective methods
        self.level_methods: dict[int, Callable | None] = {
            1: self._notify_level_1_additional,
            2: self._notify_level_2_additional,
            3: None,
            4: None,
        }

    def notify(
        self,
        fault: str,
        level: int,
        fault_status: "FaultState",
        additional_info: Optional[dict],
        fault_tag: str
    ) -> None:
        """
        Sends or clears notifications based on fault status, using fault name and location as unique tags.

        Parameters:
            fault: The fault's name, used as a unique tag for the notification.
            level: Notification level, dictating the notification type.
            additional_info: Additional fault details (optional) for the notification message.
            fault_status: Status of the fault ('active' or 'cleared').
        """

        location = (
            additional_info.get("Location") if additional_info else "Unknown Location"
        )
        message: str = f"Fault: {fault}\n"

        if additional_info:
            for key, value in additional_info.items():
                if key != "Location":  # Avoid duplicating the location in the message
                    message += f"{key}: {value}\n"

        if fault_status == FaultState.SET:
            self._process_active_fault(level, message, fault_tag)
            self.hass_app.log(
                f"Notification set for {fault} at {location} with message: {message}",
                level="DEBUG",
            )
        elif fault_status == FaultState.CLEARED:
            # Instead of sending a new "cleared" notification, we just clear the existing one.
            self._process_cleared_fault(level, fault_tag)
            self.hass_app.log(
                f"Notification cleared for {fault} at {location}",
                level="DEBUG",
            )
        else:
            self.hass_app.log(f"Invalid fault status '{fault_status}'", level="WARNING")

    def _process_active_fault(self, level: int, message: str, fault_tag: str) -> None:
        self._notify_company_app(level, message, fault_tag, FaultState.SET)
        additional_actions = self.level_methods.get(level)
        if additional_actions:
            additional_actions()
        else:
            self.hass_app.log(
                f"Notification level {level} has no additional actions",
                level="DEBUG",
            )

    def _process_cleared_fault(self, level: int, fault_tag: str) -> None:
        # Just clear the existing notification without sending a new message.
        self._clear_company_app(level, fault_tag)

    def _set_dashboard_notification(self, message: str, level: int) -> None:
        """
        Displays a notification message on the Home Assistant dashboard based on severity level.

        Parameters:
            message: The message to be displayed.
            level: The message's severity level, influencing its presentation.
        """
        # This function assumes that you have an entity in Home Assistant that represents
        # a text field on a dashboard. You would need to create this entity and configure it
        # to display messages        dashboard_entity = self.notification_config.get(f"dashboard_{level}_entity")
        if dashboard_entity:
            self.hass_app.set_state(dashboard_entity, state=message)
            self.hass_app.log(
                f"Dashboard entity {dashboard_entity} was changed to {message}",
                level="DEBUG",
            )
        else:
            self.hass_app.log(
                f"No dashboard entity configured for level '{level}'", level="WARNING"
            )

    def _notify_level_1_additional(self) -> None:
        """
        Triggers an immediate response for level 1 notifications by sounding an alarm and turning lights red.
        This method represents the highest priority action, indicating an immediate emergency.

        Args:
            message (str): The detailed message for the notification, not directly used in this method but
                           required for consistency with the interface.
        """
        self.hass_app.call_service(
            "alarm_control_panel/alarm_trigger",
            entity_id=self.notification_config["alarm_entity"],
        )
        self.hass_app.call_service(
            "light/turn_on",
            entity_id=self.notification_config["light_entity"],
            color_name="red",
        )
        self.hass_app.log(
            "Performed _notify_level_1_additional",
            level="DEBUG",
        )

    def _notify_level_2_additional(self) -> None:
        """
        Handles level 2 notifications by turning lights yellow, symbolizing a hazard that may not require
        immediate evacuation but still demands attention.

        Args:
            message (str): The detailed message for the notification, not directly used in this method but
                           required for consistency with the interface.
        """
        self.hass_app.call_service(
            "light/turn_on",
            entity_id=self.notification_config["light_entity"],
            color_name="yellow",
        )
        self.hass_app.log(
            "Performed _notify_level_2_additional",
            level="DEBUG",
        )

    def _prepare_notification_data(
        self, level: int, message: str, fault_tag: str
    ) -> dict:
        """
        Prepares the notification data based on the level and fault details.

        Args:
            level (int): The urgency level of the notification.
            fault (str): The fault identifier.
            message (str): The message to be sent.

        Returns:
            dict: The notification data ready to be sent.
        """
        base_url = "/home-safety/home_safety_overview"
        common_data = {"persistent": True, "clickAction": base_url, "tag": fault_tag}

        notification_configs = {
            1: {
                "title": "Immediate Emergency!",
                "message": message,
                "data": {
                    **common_data,
                    "color": "#FF0000",  # Red
                    "vibrationPattern": "100, 1000, 100, 1000, 100",
                    "sticky": True,
                    "notification_icon": "mdi:exit-run",
                    "importance": "high",
                },
            },
            2: {
                "title": "Hazard!",
                "message": message,
                "data": {
                    **common_data,
                    "color": "#FFA500",  # Orange
                    "sticky": True,
                    "notification_icon": "mdi:hazard-lights",
                },
            },
            3: {
                "title": "Warning!",
                "message": message,
                "data": {
                    **common_data,
                    "color": "#FFFF00",  # Yellow
                    "sticky": True,
                    "notification_icon": "mdi:home-alert",
                },
            },
            # No direct user notification for level 4
        }
        return notification_configs.get(level, {})

    def _notify_company_app(
        self, level: int, message: str, fault_tag: str, fault_state: FaultState
    ) -> None:
        """
        Sends a company app notification based on the specified level and fault details.

        Args:
            level (int): The notification level.
            fault (str): The fault identifier.
            message (str): The detailed message for the notification.
        """
        if level == 4:
            # No notification is sent for level 4.
            return

        notification_data = self._prepare_notification_data(level, message, fault_tag)
        if notification_data:
            self._handle_notify_reg(fault_tag, fault_state, notification_data)
            self._send_notification(notification_data)
            self.hass_app.log(
                f'Notification for {fault_tag}: {notification_data["title"]} | '
                f'{notification_data["message"]} | {notification_data["data"]}',
                level="DEBUG",
            )
        else:
            self.hass_app.log(
                f"No notification configuration for level {level}", level="WARNING"
            )

    def _handle_notify_reg(
        self, fault_tag: str, fault_state: FaultState, notification_data: dict
    ) -> None:
        if fault_state == FaultState.SET:
            self.active_notification[fault_tag] = notification_data
        else:
            # Remove the fault from active notifications
            if fault_tag in self.active_notification:
                del self.active_notification[fault_tag]

    def _clear_company_app(self, level: int, fault_tag: str) -> None:
        """
        Clears the previously-set notification for this fault (by tag), without sending a new message.
        """
        # Remove it from the active notifications dictionary if present.
        if fault_tag in self.active_notification:
            del self.active_notification[fault_tag]

        # If you're using the generic `notify.notify` service:
        if level != 4:
            # The tag must match the tag you originally used in _prepare_notification_data
            self.hass_app.call_service(
                "notify/notify",
                data={
                    "tag": fault_tag,
                    "clear_notification": True
                }
            )
            self.hass_app.log(
                f"Cleared notification (tag='{fault_tag}') via clear_notification request.",
                level="DEBUG",
            )

    def _send_notification(self, notification_data: dict[str, str]) -> None:
        """
        Sends a notification using the Home Assistant notification service.

        Args:
            notification_data: A dictionary containing the title, message, and additional data for the notification.
                - title (str): The title of the notification.
                - message (str): The main message body of the notification.
                - data (dict): Additional data for the notification, such as tag, color, and other attributes.
        """
        self.hass_app.call_service(
            "notify/notify",
            title=notification_data["title"],
            message=notification_data["message"],
            data=notification_data["data"],
        )

    def _add_recovery_action(self, notification_msg: str, fault_tag: str) -> None:
        """
        Adds a recovery action message to an existing active notification.

        Args:
            notification_msg: The recovery message to add.
            fault_name: The fault identifier for which to add the recovery message.
        """
        for tag, notification in self.active_notification.items():
            if tag == fault_tag:
                self._add_rec_msg(notification, notification_msg)

    def _add_rec_msg(self, notification: dict, notification_msg: str) -> None:
        """
        Appends a recovery message to an existing notification's message and resends the notification.

        Args:
            notification: The notification data dictionary to update.
            notification_msg: The recovery message to append.
        """
        notification["message"] += f" {notification_msg}"
        self._send_notification(notification)

    def _clear_symptom_msg(self, notification: dict, notification_msg: str) -> None:
        """
        Appends a recovery message to an existing notification's message and resends the notification.

        Args:
            notification: The notification data dictionary to update.
            notification_msg: The recovery message to append.
        """
        notification["message"] = f"{notification_msg}"
        self._send_notification(notification)
