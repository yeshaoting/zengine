# -*-  coding: utf-8 -*-
"""
"""

# Copyright (C) 2015 ZetaOps Inc.
#
# This file is licensed under the GNU General Public License v3
# (GPLv3).  See LICENSE.txt for details.
import json

import pika

from pyoko import Model, field, ListNode
from pyoko.conf import settings
from pyoko.exceptions import IntegrityError
from pyoko.lib.utils import get_object_from_path
from zengine.client_queue import BLOCKING_MQ_PARAMS
from zengine.lib.utils import to_safe_str

UserModel = get_object_from_path(settings.USER_MODEL)


def get_mq_connection():
    connection = pika.BlockingConnection(BLOCKING_MQ_PARAMS)
    channel = connection.channel()
    return connection, channel


CHANNEL_TYPES = (
    # users private message hub
    (5, "Private"),
    # system notifications of user
    # (10, "Notify"),
    #  a One-To-One communication between 2 user
    (10, "Direct"),
    # public chat rooms
    (15, "Public"),
)


class Channel(Model):
    """
    Represents MQ exchanges.

    is_private: Represents users exchange hub
    Each user have a durable private exchange,
     which their code_name composed from user key prefixed with "prv_"

    is_direct: Represents a user-to-user direct message exchange
    """
    mq_channel = None
    mq_connection = None

    typ = field.Integer("Type", choices=CHANNEL_TYPES)
    name = field.String("Name")
    code_name = field.String("Internal name")
    description = field.String("Description")
    owner = UserModel(reverse_name='created_channels', null=True)

    class Managers(ListNode):
        user = UserModel()

    @classmethod
    def get_or_create_direct_channel(cls, initiator, receiver):
        """
        Creates a  direct messaging channel between two user

        Args:
            initiator: User, who sent the first message
            receiver: User, other party

        Returns:
            Channel
        """
        existing = cls.objects.OR().filter(
            code_name='%s_%s' % (initiator.key, receiver.key)).filter(
            code_name='%s_%s' % (receiver.key, initiator.key))
        if existing:
            return existing[0]
        else:
            channel_name = '%s_%s' % (initiator.key, receiver.key)
            channel = cls(is_direct=True, code_name=channel_name).save()
            Subscriber(channel=channel, user=initiator).save()
            Subscriber(channel=channel, user=receiver).save()
            return channel

    @classmethod
    def add_message(cls, channel_key, body, title=None, sender=None, url=None, typ=2,
                    receiver=None):
        mq_channel = cls._connect_mq()
        mq_msg = json.dumps(dict(sender=sender, body=body, msg_title=title, url=url, typ=typ))
        mq_channel.basic_publish(exchange=channel_key, routing_key='', body=mq_msg)
        return Message(sender=sender, body=body, msg_title=title, url=url,
                       typ=typ, channel_id=channel_key, receiver=receiver).save()

    def get_last_messages(self):
        # TODO: Refactor this with RabbitMQ Last Cached Messages exchange
        return self.message_set.objects.filter()[:20]

    @classmethod
    def _connect_mq(cls):
        if cls.mq_connection is None or cls.mq_connection.is_closed:
            cls.mq_connection, cls.mq_channel = get_mq_connection()
        return cls.mq_channel

    def create_exchange(self):
        """
        Creates MQ exchange for this channel
        Needs to be defined only once.
        """
        mq_channel = self._connect_mq()
        mq_channel.exchange_declare(exchange=self.code_name,
                                    exchange_type='fanout',
                                    durable=True)

    def get_actions_for(self, user):
        actions = [
            ('Pin', 'pin_channel')
        ]
        if self.sender == user:
            actions.extend([
                ('Delete', 'zops_delete_channel'),
                ('Edit', 'zops_edit_channel')
            ])

    def pre_creation(self):
        if not self.code_name:
            if self.name:
                self.code_name = to_safe_str(self.name)
                self.key = self.code_name
                return
            if self.owner and self.is_private:
                self.code_name = self.owner.prv_exchange
                self.key = self.code_name
                return
            raise IntegrityError('Non-private and non-direct channels should have a "name".')
        else:
            self.key = self.code_name

    def post_creation(self):
        self.create_exchange()


class Subscriber(Model):
    """
    Permission model
    """

    channel = Channel()
    user = UserModel(reverse_name='subscriptions')
    is_muted = field.Boolean("Mute the channel", default=False)
    inform_me = field.Boolean("Inform when I'm mentioned", default=True)
    is_visible = field.Boolean("Show under user's channel list", default=True)
    can_leave = field.Boolean("Membership is not obligatory", default=True)
    last_seen_msg_time = field.DateTime("Last seen message's time")

    # status = field.Integer("Status", choices=SUBSCRIPTION_STATUS)

    @classmethod
    def _connect_mq(cls):
        if cls.connection is None or cls.connection.is_closed:
            cls.connection, cls.channel = get_mq_connection()
        return cls.channel

    def unread_count(self):
        # FIXME: track and return actual unread message count
        return self.channel.message_set.objects.filter(
            timestamp__lt=self.last_seen_msg_time).count()

    def create_exchange(self):
        """
        Creates user's private exchange

        Actually user's private channel needed to be defined only once,
        and this should be happened when user first created.
        But since this has a little performance cost,
        to be safe we always call it before binding to the channel we currently subscribe
        """
        channel = self._connect_mq()
        channel.exchange_declare(exchange='prv_%s' % self.user.key.lower(),
                                 exchange_type='fanout',
                                 durable=True)

    @classmethod
    def mark_seen(cls, key, datetime_str):
        cls.objects.filter(key=key).update(last_seen=datetime_str)

    def bind_to_channel(self):
        """
        Binds (subscribes) users private exchange to channel exchange
        Automatically called at creation of subscription record.
        """
        channel = self._connect_mq()
        channel.exchange_bind(source=self.channel.code_name, destination=self.user.key)

    def post_creation(self):
        self.create_exchange()
        self.bind_to_channel()

    def __unicode__(self):
        return "%s in %s" % (self.user, self.channel.name)


MSG_TYPES = (
    (1, "Info Notification"),
    (11, "Error Notification"),
    (111, "Success Notification"),
    (2, "Direct Message"),
    (3, "Broadcast Message"),
    (4, "Channel Message")
)
MESSAGE_STATUS = (
    (1, "Created"),
    (11, "Transmitted"),
    (22, "Seen"),
    (33, "Read"),
    (44, "Archived"),

)


class Message(Model):
    """
    Message model

    Notes:
        Never use directly for creating new messages! Use these methods:
            - Channel objects's **add_message()** method.
            - User object's **set_message()** method. (which also uses channel.add_message)
    """
    channel = Channel()
    sender = UserModel(reverse_name='sent_messages')
    receiver = UserModel(reverse_name='received_messages')
    typ = field.Integer("Type", choices=MSG_TYPES, default=1)
    status = field.Integer("Status", choices=MESSAGE_STATUS, default=1)
    msg_title = field.String("Title")
    body = field.String("Body")
    url = field.String("URL")

    def get_actions_for(self, user):
        actions = [
            ('Favorite', 'favorite_message')
        ]
        if self.sender == user:
            actions.extend([
                ('Delete', 'zops_delete_message'),
                ('Edit', 'zops_edit_message')
            ])
        else:
            actions.extend([
                ('Flag', 'flag_message')
            ])

    def serialize_for(self, user):
        return {
            'content': self.body,
            'type': self.typ,
            'time': self.updated_at,
            'attachments': [attachment.serialize() for attachment in self.attachment_set],
            'title': self.msg_title,
            'sender_name': self.sender.full_name,
            'sender_key': self.sender.key,
            'key': self.key,
            'actions': self.get_actions_for(user),
        }

    def __unicode__(self):
        content = self.msg_title or self.body
        return "%s%s" % (content[:30], '...' if len(content) > 30 else '')


ATTACHMENT_TYPES = (
    (1, "Document"),
    (11, "Spreadsheet"),
    (22, "Image"),
    (33, "PDF"),

)


class Attachment(Model):
    """
    A model to store message attachments
    """
    file = field.File("File", random_name=True, required=False)
    typ = field.Integer("Type", choices=ATTACHMENT_TYPES)
    name = field.String("File Name")
    description = field.String("Description")
    channel = Channel()
    message = Message()

    def serialize(self):
        return {
            'description': self.description,
            'file_name': self.name,
            'url': "%s%s" % (settings.S3_PUBLIC_URL, self.file)
        }

    def __unicode__(self):
        return self.name


class Favorite(Model):
    """
    A model to store users bookmarked messages
    """
    channel = Channel()
    user = UserModel()
    message = Message()
