import asyncio
import aiomqtt
import json
import random
import time
from typing import Any
from typing import Optional, Callable
import logging
import textwrap


class TopicPayload:
    def __init__(self, config, local_context: dict[str, Any]):
        self.local_context = local_context
        self.config = config
        self.get_populated()

    def get_populated(self):
        return self.recursive_replace(self.config)

    def replace_str(self, string: str):
        try:
            return eval(string, self.local_context, self.local_context)
        except Exception as e:
            raise ValueError(f"Failed to replace '{string}': {e}")

    def recursive_replace(self, config_part):
        if isinstance(config_part, dict):
            buffer_obj = {}
            for key, value in config_part.items():
                buffer_obj[self.recursive_replace(key)] = self.recursive_replace(value)
            return buffer_obj
        elif isinstance(config_part, list):
            buffer_obj = []
            for item in config_part:
                buffer_obj.append(self.recursive_replace(item))
            return buffer_obj
        elif isinstance(config_part, str):
            return self.replace_str(config_part)
        else:
            return config_part


class TopicTrigger:
    delay: Optional[float]
    interval: Optional[float]
    condition: Optional[Callable[[], bool]]
    last_interval_trigger: float
    last_delay_trigger: float

    _parent_link: "TopicTriggerCollection"

    def __init__(
        self,
        config: dict,
        local_context: dict[str, Any],
        parent_link: "TopicTriggerCollection",
        logger: logging.Logger,
    ):
        self.logger = logger
        self._parent_link = parent_link
        if not isinstance(config, dict):
            raise TypeError("Config for sendOn must be a dict")
        self.config = config

        self.local_context = local_context

        self.delay = None
        self.interval = None
        self.condition = None
        self.last_interval_trigger = 0
        self.last_delay_trigger = 0

        self.prepare()

    def prepare(self):
        for key, value in self.config.items():
            if key == "equation":
                # try to eval
                # self.config[key] =  self.config[key]
                try:

                    self.condition = lambda: eval(
                        self.config["equation"], self.local_context, self.local_context
                    )
                    self.condition()
                except Exception as e:
                    raise ValueError(f"Failed to eval '{self.config[key]}': {e}")
                # Test the condition to ensure it returns a bool
                try:
                    result = self.condition()
                    if not isinstance(result, bool):
                        raise ValueError(
                            "equation condition must return a boolean value"
                        )
                except Exception as e:
                    raise ValueError(f"Failed to execute equation condition: {e}")
            if key == "interval":
                try:
                    float(value)
                except (TypeError, ValueError):
                    raise ValueError(
                        f"Interval value '{value}' is not convertible to float"
                    )
                self.last_interval_trigger = time.monotonic() - float(value)
                self.interval = float(value)
            if key == "delay":
                try:
                    float(value)
                except (TypeError, ValueError):
                    raise ValueError(
                        f"Interval value '{value}' is not convertible to float"
                    )
                self.last_delay_trigger = time.monotonic() - float(value)
                self.delay = float(value)
        self.get_query_interval()

    async def check(self):
        # delay is first priority, interval second and executable condition is last
        if self.delay is not None:
            now = time.monotonic()
            if now - self.last_delay_trigger < self.delay:
                return False
            self.last_delay_trigger = now

        if self.interval is not None:
            now = time.monotonic()
            if now - self.last_interval_trigger < self.interval:
                return False
            self.last_interval_trigger = now

        if self.condition is not None:
            try:
                return bool(self.condition())
            except Exception as e:
                raise ValueError(f"Failed to execute toEval: {e}")

        return True

    def get_query_interval(self) -> float:
        min_interval = None
        if self.delay is not None:
            min_interval = self.delay
        if self.interval is not None:
            if min_interval is None:
                min_interval = self.interval
            else:
                min_interval = min(min_interval, self.interval)

        if min_interval is None:
            min_interval = 1.0  # default to sensible delay
        return min_interval

    async def query_loop(self):
        interval = self.get_query_interval()
        while interval is not None:
            try:
                if await self.check():
                    try:
                        await self._parent_link._parent_link.send()
                    except Exception as e:
                        self.logger.error(
                            f"Failed to post message: {e} | Trigger config: {self.config}"
                        )
            except Exception as e:
                self.logger.error(f"Failed to check trigger: {e}")
            await asyncio.sleep(interval)


class TopicTriggerCollection:
    post_message_callback: lambda x: None = None
    trigger_list: list[TopicTrigger] = []
    trigger_coros_list: list[asyncio.Task] = []

    _parent_link: "OutputTopic"

    def __init__(
        self,
        config: list,
        local_context,
        _parent_link: "OutputTopic",
        logger: logging.Logger,
    ):
        self.logger = logger
        self._parent_link = _parent_link
        self.config = config
        self.local_context = local_context

        if not isinstance(config, list):
            raise TypeError("Config for TopicTriggerCollection must be a list")

        for trigger_config in config:
            trigger = TopicTrigger(trigger_config, local_context, self, self.logger)
            self.trigger_list.append(trigger)
            self.trigger_coros_list.append(trigger.query_loop())


class OutputTopic:
    name: str
    logger: logging.Logger
    payload: TopicPayload
    trigger_collection: TopicTriggerCollection

    def __init__(
        self,
        config: dict[str, Any],
        name: str,
        client: aiomqtt.Client,
        local_context: dict[str, Any],
        logger: logging.Logger,
    ):
        self.logger = logger
        self.local_context = local_context
        self.client = client

        if "payload" not in config or "sendOn" not in config:
            raise KeyError(
                "Both 'payload' and 'sendOn' keys must be present in the config"
            )
        self.config = config
        self.name = name
        self.payload = TopicPayload(config["payload"], self.local_context)
        self.trigger_collection = TopicTriggerCollection(
            config["sendOn"], self.local_context, self, self.logger
        )

    async def send(self):
        payload = self.payload.get_populated()
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        await self.client.publish(self.name, payload)

    def get_corutines(self):
        return self.trigger_collection.trigger_coros_list

class OutputTopicCollection:
    def __init__(
        self,
        config: dict[str, Any],
        client: aiomqtt.Client,
        local_context: dict[str, Any],
        logger: logging.Logger,
    ):
        self.config = config
        self.logger = logger
        self.local_context = local_context
        self.client = client
        self.topics = {}

        if not isinstance(config, dict):
            raise TypeError("Config for OutputTopicCollection must be a dict")
        for name, topic_config in self.config.items():
            self.topics[name] = OutputTopic(
                topic_config, name, self.client, self.local_context, self.logger
            )

    def get_coroutines(self):
        coroutines = []
        for topic in self.topics.values():
            coroutines.extend(topic.get_corutines())
        return coroutines

          

class InputTopicAction:
    _parent_link: "InputTopic"

    def __init__(
        self, action: str, _parent_link: "InputTopic", local_context: dict[str, Any]
    ):
        self.action_str = action
        self._parent_link = _parent_link
        self.local_context = dict({x: w for x, w in local_context.items()})
        write_func_body = self.action_str.split(":", 1)[1]
        write_func_args = "x"
        if "await" in self.action_str:

            asyncFunc = f"""
            async def _action({', '.join(write_func_args)}):
                return {write_func_body}
            """
            asyncFunc = textwrap.dedent(asyncFunc)
            exec(asyncFunc, self.local_context, self.local_context)
            action_func = self.local_context["_action"]

            async def do_action(x):
                try:
                    return await action_func(x)
                except Exception as e:
                    raise RuntimeError(
                        f"Error occurred while executing write coro: {e}"
                    )

        else:
            try:
                action_func = eval(
                    f"lambda {self.action_str}", self.local_context, self.local_context
                )
            except:
                raise ValueError(
                    f"Failed to evaluate writeAs function: {self.action_str}"
                )

            async def do_action(x):
                try:
                    return action_func(x)
                except Exception as e:
                    raise RuntimeError(
                        f"Error occurred while executing write_as coro: {e}"
                    )

        self.do_acton = do_action

    async def run_action(self, x):
        try:
            return await self.do_acton(x)
        except Exception as e:
            self._parent_link.logger.error(f"Error in InputTopicAction.run_action: {e}")
            return None


class InputTopic:
    action_list: list[InputTopicAction]
    name: str

    _parent_link: "InputTopicCollection"

    def __init__(
        self,
        name: str,
        config: dict[str, Any],
        client: aiomqtt.Client,
        local_context: dict[str, Any],
        _parent_link: "InputTopicCollection",
        logger: logging.Logger,
    ):
        self.name = name
        self.logger = logger
        self.local_context = local_context
        self.client = client
        self._parent_link = _parent_link
        if not isinstance(config, dict):
            raise TypeError("Config for inputTopic must be a dict")
        self.action_list = []
        if not "onRecieve" in config:
            raise ValueError("add onRecieve key to the subscriben topic config")
        if not isinstance(config["onRecieve"], list):
            raise TypeError("'onRecieve' must be a list")

        for action in config["onRecieve"]:
            self.action_list.append(InputTopicAction(action, self, self.local_context))

    async def run_actions(self, x):
        return await asyncio.gather(
            *(action.run_action(x) for action in self.action_list)
        )

    async def subscribe(self):
        await self.client.subscribe(self.name)


class InputTopicCollection:
    def __init__(
        self,
        config: dict[str, Any],
        client: aiomqtt.Client,
        local_context: dict[str, Any],
        logger: logging.Logger,
    ):
        self.config = config
        self.logger = logger
        self.local_context = local_context
        self.client = client

        self.topics = {}

        for name, actons_config in self.config.items():
            self.topics[name] = InputTopic(
                name, actons_config, self.client, self.local_context, self, self.logger
            )

    async def run_subcribe(self):
        await asyncio.gather(*(topic.subscribe() for topic in self.topics.values()))

    async def run_routing(self):
        async for message in self.client.messages:
            topic = self.topics.get(message.topic.value)
            if topic:
                payload = (
                    message.payload.decode()
                    if hasattr(message.payload, "decode")
                    else message.payload
                )
                await topic.run_actions(payload)
            else:
                self.logger.warning(
                    f"Received message for unknown topic: {message.topic}"
                )


