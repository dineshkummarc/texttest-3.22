#!/usr/bin/env python

import datetime

class mydate(datetime.date):
    @classmethod
    def mytodayfunction(cls):
        return datetime.date(2010, 2, 18)

datetime.date = mydate
