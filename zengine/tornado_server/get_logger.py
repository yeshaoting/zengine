# -*-  coding: utf-8 -*-
"""
"""

# Copyright (C) 2015 ZetaOps Inc.
#
# This file is licensed under the GNU General Public License v3
# (GPLv3).  See LICENSE.txt for details.
import logging
import os


def get_logger(settings):
    # create logger
    logger = logging.getLogger(os.path.basename(settings.LOG_FILE).split('.')[0])
    logger.setLevel(getattr(logging, settings.LOG_LEVEL))
    logger.propagate = False
    # create console handler and set level to debug
    if settings.LOG_HANDLER == 'file':
        ch = logging.FileHandler(filename=settings.LOG_FILE, mode="w")
    else:
        ch = logging.StreamHandler()
    # ch.setLevel(logging.DEBUG)

    # create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(pathname)s:%(lineno)d [%(module)s > %(funcName)s] - %(name)s - %(levelname)s - %(message)s')

    # add formatter to ch
    ch.setFormatter(formatter)

    # add ch to logger
    logger.addHandler(ch)
    return logger
