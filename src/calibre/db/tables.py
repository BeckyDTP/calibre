#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2011, Kovid Goyal <kovid@kovidgoyal.net>'
__docformat__ = 'restructuredtext en'

from datetime import datetime

from dateutil.tz import tzoffset

from calibre.constants import plugins
from calibre.utils.date import parse_date, local_tz
from calibre.ebooks.metadata import author_to_author_sort

_c_speedup = plugins['speedup'][0]

def _c_convert_timestamp(val):
    if not val:
        return None
    try:
        ret = _c_speedup.parse_date(val.strip())
    except:
        ret = None
    if ret is None:
        return parse_date(val, as_utc=False)
    year, month, day, hour, minutes, seconds, tzsecs = ret
    return datetime(year, month, day, hour, minutes, seconds,
                tzinfo=tzoffset(None, tzsecs)).astimezone(local_tz)

class Table(object):

    def __init__(self, name, metadata, link_table=None):
        self.name, self.metadata = name, metadata

        # self.adapt() maps values from the db to python objects
        self.adapt = \
            {
                'datetime': _c_convert_timestamp,
                'bool': bool
            }.get(
                metadata['datatype'], lambda x: x)
        if name == 'authors':
            # Legacy
            self.adapt = lambda x: x.replace('|', ',') if x else None

        self.link_table = (link_table if link_table else
                'books_%s_link'%self.metadata['table'])

class OneToOneTable(Table):

    '''
    Represents data that is unique per book (it may not actually be unique) but
    each item is assigned to a book in a one-to-one mapping. For example: uuid,
    timestamp, size, etc.
    '''

    def read(self, db):
        self.book_col_map = {}
        idcol = 'id' if self.metadata['table'] == 'books' else 'book'
        for row in db.conn.execute('SELECT {0}, {1} FROM {2}'.format(idcol,
            self.metadata['column'], self.metadata['table'])):
            self.book_col_map[row[0]] = self.adapt(row[1])

class SizeTable(OneToOneTable):

    def read(self, db):
        self.book_col_map = {}
        for row in db.conn.execute(
                'SELECT books.id, (SELECT MAX(uncompressed_size) FROM data '
                'WHERE data.book=books.id) FROM books'):
            self.book_col_map[row[0]] = self.adapt(row[1])

class ManyToOneTable(Table):

    '''
    Represents data where one data item can map to many books, for example:
    series or publisher.

    Each book however has only one value for data of this type.
    '''

    def read(self, db):
        self.id_map = {}
        self.extra_map = {}
        self.col_book_map = {}
        self.book_col_map = {}
        self.read_id_maps(db)
        self.read_maps(db)

    def read_id_maps(self, db):
        for row in db.conn.execute('SELECT id, {0} FROM {1}'.format(
            self.metadata['name'], self.metadata['table'])):
            if row[1]:
                self.id_map[row[0]] = self.adapt(row[1])

    def read_maps(self, db):
        for row in db.conn.execute(
                'SELECT book, {0} FROM {1}'.format(
                    self.metadata['link_column'], self.link_table)):
            if row[1] not in self.col_book_map:
                self.col_book_map[row[1]] = []
            self.col_book_map.append(row[0])
            self.book_col_map[row[0]] = row[1]

class ManyToManyTable(ManyToOneTable):

    '''
    Represents data that has a many-to-many mapping with books. i.e. each book
    can have more than one value and each value can be mapped to more than one
    book. For example: tags or authors.
    '''

    def read_maps(self, db):
        for row in db.conn.execute(
                'SELECT book, {0} FROM {1}'.format(
                    self.metadata['link_column'], self.link_table)):
            if row[1] not in self.col_book_map:
                self.col_book_map[row[1]] = []
            self.col_book_map.append(row[0])
            if row[0] not in self.book_col_map:
                self.book_col_map[row[0]] = []
            self.book_col_map[row[0]].append(row[1])

class AuthorsTable(ManyToManyTable):

    def read_id_maps(self, db):
        self.alink_map = {}
        for row in db.conn.execute(
                'SELECT id, name, sort, link FROM authors'):
            self.id_map[row[0]] = row[1]
            self.extra_map[row[0]] = (row[2] if row[2] else
                    author_to_author_sort(row[1]))
            self.alink_map[row[0]] = row[3]

class FormatsTable(ManyToManyTable):

    def read_id_maps(self, db):
        pass

    def read_maps(self, db):
        for row in db.conn.execute('SELECT book, format, name FROM data'):
            if row[1] is not None:
                if row[1] not in self.col_book_map:
                    self.col_book_map[row[1]] = []
                self.col_book_map.append(row[0])
                if row[0] not in self.book_col_map:
                    self.book_col_map[row[0]] = []
                self.book_col_map[row[0]].append((row[1], row[2]))

class IdentifiersTable(ManyToManyTable):

    def read_id_maps(self, db):
        pass

    def read_maps(self, db):
        for row in db.conn.execute('SELECT book, type, val FROM identifiers'):
            if row[1] is not None and row[2] is not None:
                if row[1] not in self.col_book_map:
                    self.col_book_map[row[1]] = []
                self.col_book_map.append(row[0])
                if row[0] not in self.book_col_map:
                    self.book_col_map[row[0]] = []
                self.book_col_map[row[0]].append((row[1], row[2]))

