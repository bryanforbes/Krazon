#!/usr/bin/env python

import asyncio
import uvloop

from botus_receptus import cli
from krazon import Krazon

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


if __name__ == '__main__':
    runner = cli(Krazon, './config.ini')
    runner()
