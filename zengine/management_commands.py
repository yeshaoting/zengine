# -*-  coding: utf-8 -*-
"""
"""

# Copyright (C) 2015 ZetaOps Inc.
#
# This file is licensed under the GNU General Public License v3
# (GPLv3).  See LICENSE.txt for details.
from pyoko.manage import *


class UpdatePermissions(Command):
    CMD_NAME = 'update_permissions'
    HELP = 'Syncs permissions with DB'

    def run(self):
        from pyoko.lib.utils import get_object_from_path
        from zengine.auth.permissions import get_all_permissions
        from zengine.config import settings
        model = get_object_from_path(settings.PERMISSION_MODEL)
        perms = []
        new_perms = []
        for code, name, desc in get_all_permissions():
            perm, new = model.objects.get_or_create({'description': desc}, code=code, name=name)
            perms.append(perm)
            if new:
                new_perms.append(perm)

        if len(perms) == len(new_perms):
            report = ''
        else:
            report = "\nTotal %s permission exist. " % len(perms)
        report += "\n%s new permission record added.\n\n" % len(new_perms)
        if new_perms:
            report = "\n + " + "\n + ".join([p.name for p in new_perms]) + report
        return report


class CreateUser(Command):
    CMD_NAME = 'create_user'
    HELP = 'Creates a new user'
    PARAMS = [
        {'name': 'username', 'required': True, 'help': 'Login username'},
        {'name': 'password', 'required': True, 'help': 'Login password'},
        {'name': 'super', 'action': 'store_true', 'help': 'This is a super user'},
    ]

    def run(self):
        from zengine.models import User
        user = User(username=self.manager.args.username, superuser=self.manager.args.super)
        user.set_password(self.manager.args.password)
        user.save()
        return "New user created with ID: %s" % user.key


class RunServer(Command):
    CMD_NAME = 'runserver'
    HELP = 'Run the development server'
    PARAMS = [
        {'name': 'addr', 'default': '127.0.0.1', 'help': 'Listening address. Defaults to 127.0.0.1'},
        {'name': 'port', 'default': '9001', 'help': 'Listening port. Defaults to 9001'},
    ]

    def run(self):
        from wsgiref import simple_server
        from zengine.server import app
        httpd = simple_server.make_server(self.manager.args.addr, int(self.manager.args.port), app)
        print("Development server started on http://%s:%s. \n\nPress Ctrl+C to stop\n" % (
            self.manager.args.addr,
            self.manager.args.port)
              )
        httpd.serve_forever()