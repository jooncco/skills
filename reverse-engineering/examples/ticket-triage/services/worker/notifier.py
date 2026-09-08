"""Fan-out of triage results to downstream channels."""
from __future__ import annotations

import logging

import boto3
import httpx

log = logging.getLogger(__name__)
_sns = boto3.client("sns")


class Notifier:
    def __init__(self, slack_webhook: str = "", topic_arn: str = "") -> None:
        self._slack = slack_webhook
        self._topic = topic_arn

    def notify(self, result: dict) -> None:
        if self._topic:
            _sns.publish(TopicArn=self._topic, Message=str(result))
        if self._slack:
            # NOTE: synchronous call inside the worker loop; blocks the consumer
            httpx.post(self._slack, json={"text": f"triage: {result}"}, timeout=10)
