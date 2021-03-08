# -*- encoding: utf-8 -*-
"""

    Tokenizer for Icelandic text

    Copyright (C) 2020 Miðeind ehf.
    Original author: Vilhjálmur Þorsteinsson

    This software is licensed under the MIT License:

        Permission is hereby granted, free of charge, to any person
        obtaining a copy of this software and associated documentation
        files (the "Software"), to deal in the Software without restriction,
        including without limitation the rights to use, copy, modify, merge,
        publish, distribute, sublicense, and/or sell copies of the Software,
        and to permit persons to whom the Software is furnished to do so,
        subject to the following conditions:

        The above copyright notice and this permission notice shall be
        included in all copies or substantial portions of the Software.

        THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
        EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
        MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
        IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
        CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
        TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
        SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


    The function tokenize() consumes a text string and
    returns a generator of tokens. Each token is a
    named tuple, having the form (kind, txt, val),
    where kind is one of the constants specified in the
    TOK class, txt is the original source text,
    and val contains auxiliary information
    depending on the token type (such as the meaning of
    an abbreviation, or the day, month and year for dates).

"""

from __future__ import absolute_import
from __future__ import unicode_literals

from dataclasses import dataclass
from typing import Any, List, Optional

import re
import datetime
import unicodedata

from .abbrev import Abbreviations

# pylint: disable=unused-wildcard-import
from .definitions import *


@dataclass() # TODO: Does this still make sense?
class Tok:
    # Type of token
    kind: int
    # Text of the token
    txt: str
    # Value of the token (e.g. if it is a date or currency)
    val: Any

    # The full original string of this token
    _original: Optional[str] = None # If this is none then we're not tracking origins
    # Each index in _origin_spans maps from 'txt' (which may have substitutions) to 'original'
    # This is required to preserve 'original' correctly when splitting
    _origin_spans: Optional[List[int]] = None


    def split(self, pos: int):
        """
        Split this token into two at 'pos'.

        The first token returned will have 'pos' characters and the second one will have the rest.

        """
        # TODO: What happens if you split a token that has txt=="" and _original!=""?
        # TODO: What should we do with val?

        if self._is_tracking_original():
            if pos >= len(self._origin_spans):
                l = Tok(self.kind, self.txt, self.val, self._original, self._origin_spans)
                r = Tok(self.kind, "", None, "", [])
            else:
                l = Tok(self.kind, self.txt[:pos], self.val,
                        self._original[:self._origin_spans[pos]], self._origin_spans[:pos])
                r = Tok(self.kind, self.txt[pos:], self.val,
                        self._original[self._origin_spans[pos]:],
                        [x-self._origin_spans[pos] for x in self._origin_spans[pos:]])
        else:
            l = Tok(self.kind, self.txt[:pos], self.val)
            r = Tok(self.kind, self.txt[pos:], self.val)

        return l, r


    def substitute(self, span, new):
        """ Substitute a span with a single or empty character 'new'. """
        substitute_length = span[1]-span[0]

        self.txt = self.txt[:span[0]] + new + self.txt[span[1]:]

        if self._is_tracking_original():
            # Remove origin entries that correspond to characters that are gone.
            self._origin_spans = self._origin_spans[:span[0]+len(new)] + self._origin_spans[span[1]:]


    def substitute_all(self, old_char, new_char):
        """ Substitute all occurrences of 'old_char' with 'new_char'.
            The new character may be empty.
        """
        # TODO: Support arbitrary length substitutions? What does that do to origin tracking?

        assert len(old_char) == 1, f"'old_char' ({old_char}) was not of length 1"
        assert len(new_char) == 0 or len(new_char) == 1, f"'new_char' ({new_char}) was too long."

        i = 0
        for c in self.txt:
            if c == old_char:
                self.substitute((i, i+1), new_char)
                i += len(new_char)
            else:
                i += 1


    def concatenate(self, other, *, separator=""):
        """ Return a new token that consists of self with other concatenated to the end.
            A separator can optionally be supplied.
        """
        new_kind = self.kind # XXX: This is a guess. We'll probably change this just after?
        new_txt = self.txt + separator + other.txt
        new_val = self.val # XXX: Probably wrong?
        new_original = self._original + other._original
        separator_origin_spans = [len(self._original)]*len(separator) if len(other._origin_spans) > 0 else []
        new_origin_spans = self._origin_spans \
                + separator_origin_spans \
                + [i + len(self._original) for i in other._origin_spans]

        return Tok(new_kind, new_txt, new_val, new_original, new_origin_spans)


    def _is_tracking_original(self):
        return self._original is not None and self._origin_spans is not None


class TOK:

    """ Token types """
    # Raw minimally processed token
    RAW = -1

    # Punctuation
    PUNCTUATION = 1
    # Time hh:mm:ss
    TIME = 2
    # Date yyyy-mm-dd
    DATE = 3
    # Year, four digits
    YEAR = 4
    # Number, integer or real
    NUMBER = 5
    # Word, which may contain hyphens and apostrophes
    WORD = 6
    # Telephone number: 7 digits, eventually preceded by country code
    TELNO = 7
    # Percentage (number followed by percent or promille sign)
    PERCENT = 8
    # A Uniform Resource Locator (URL): https://example.com/path?p=100
    URL = 9
    # An ordinal number, eventually using Roman numerals (1., XVII.)
    ORDINAL = 10
    # A timestamp (not emitted by Tokenizer)
    TIMESTAMP = 11
    # A currency sign or code
    CURRENCY = 12
    # An amount, i.e. a quantity with a currency code
    AMOUNT = 13
    # Person name (not used by Tokenizer)
    PERSON = 14
    # E-mail address (somebody@somewhere.com)
    EMAIL = 15
    # Entity name (not used by Tokenizer)
    ENTITY = 16
    # Unknown token type
    UNKNOWN = 17
    # Absolute date
    DATEABS = 18
    # Relative date
    DATEREL = 19
    # Absolute time stamp, yyyy-mm-dd hh:mm:ss
    TIMESTAMPABS = 20
    # Relative time stamp, yyyy-mm-dd hh:mm:ss
    # where at least of yyyy, mm or dd is missing
    TIMESTAMPREL = 21
    # A measured quantity with its unit (220V, 0.5 km)
    MEASUREMENT = 22
    # Number followed by letter (a-z), often seen in addresses (Skógarstígur 4B)
    NUMWLETTER = 23
    # Internet domain name (an.example.com)
    DOMAIN = 24
    # Hash tag (#metoo)
    HASHTAG = 25
    # Chemical compound ('H2SO4')
    MOLECULE = 26
    # Social security number ('kennitala')
    SSN = 27
    # Social media user name ('@username_123')
    USERNAME = 28
    # Serial number ('394-8362')
    SERIALNUMBER = 29
    # Company name ('Google Inc.')
    COMPANY = 30
    # Sentence split token
    S_SPLIT = 10000
    # Paragraph begin
    P_BEGIN = 10001
    # Paragraph end
    P_END = 10002
    # Sentence begin
    S_BEGIN = 11001
    # Sentence end
    S_END = 11002
    # End sentinel
    X_END = 12001

    END = frozenset((P_END, S_END, X_END, S_SPLIT))
    TEXT = frozenset((WORD, PERSON, ENTITY, MOLECULE, COMPANY))
    TEXT_EXCL_PERSON = frozenset((WORD, ENTITY, MOLECULE, COMPANY))

    # Token descriptive names

    descr = {
        PUNCTUATION: "PUNCTUATION",
        TIME: "TIME",
        TIMESTAMP: "TIMESTAMP",
        TIMESTAMPABS: "TIMESTAMPABS",
        TIMESTAMPREL: "TIMESTAMPREL",
        DATE: "DATE",
        DATEABS: "DATEABS",
        DATEREL: "DATEREL",
        YEAR: "YEAR",
        NUMBER: "NUMBER",
        NUMWLETTER: "NUMWLETTER",
        CURRENCY: "CURRENCY",
        AMOUNT: "AMOUNT",
        MEASUREMENT: "MEASUREMENT",
        PERSON: "PERSON",
        WORD: "WORD",
        UNKNOWN: "UNKNOWN",
        TELNO: "TELNO",
        PERCENT: "PERCENT",
        URL: "URL",
        DOMAIN: "DOMAIN",
        HASHTAG: "HASHTAG",
        EMAIL: "EMAIL",
        ORDINAL: "ORDINAL",
        ENTITY: "ENTITY",
        MOLECULE: "MOLECULE",
        SSN: "SSN",
        USERNAME: "USERNAME",
        SERIALNUMBER: "SERIALNUMBER",
        COMPANY: "COMPANY",
        S_SPLIT: "SPLIT SENT",
        P_BEGIN: "BEGIN PARA",
        P_END: "END PARA",
        S_BEGIN: "BEGIN SENT",
        S_END: "END SENT",
    }

    # Token constructors

    @staticmethod
    def Punctuation(t, normalized=None):
        tp = TP_CENTER  # Default punctuation type
        if normalized is None:
            normalized = t.txt
        if normalized and len(normalized) == 1:
            if normalized in LEFT_PUNCTUATION:
                tp = TP_LEFT
            elif normalized in RIGHT_PUNCTUATION:
                tp = TP_RIGHT
            elif normalized in NONE_PUNCTUATION:
                tp = TP_NONE
        t.kind = TOK.PUNCTUATION
        t.val = (tp, normalized)
        return t

    @staticmethod
    def Time(t, h, m, s):
        t.kind = TOK.TIME
        t.val = (h, m, s)
        return t

    @staticmethod
    def Date(t, y, m, d):
        t.kind = TOK.DATE
        t.val = (y, m, d)
        return t

    @staticmethod
    def Dateabs(t, y, m, d):
        t.kind = TOK.DATEABS
        t.val = (y, m, d)
        return t

    @staticmethod
    def Daterel(t, y, m, d):
        t.kind = TOK.DATEREL
        t.val = (y, m, d)
        return t

    @staticmethod
    def Timestamp(t, y, mo, d, h, m, s):
        t.kind = TOK.TIMESTAMP
        t.val = (y, mo, d, h, m, s)
        return t

    @staticmethod
    def Timestampabs(t, y, mo, d, h, m, s):
        t.kind = TOK.TIMESTAMPABS
        t.val = (y, mo, d, h, m, s)
        return t

    @staticmethod
    def Timestamprel(t, y, mo, d, h, m, s):
        t.kind = TOK.TIMESTAMPREL
        t.val = (y, mo, d, h, m, s)
        return t

    @staticmethod
    def Year(t, n):
        t.kind = TOK.YEAR
        t.val = n
        return t

    @staticmethod
    def Telno(t, telno, cc="354"):
        # The w parameter is the original token text,
        # while telno has the standard form 'DDD-DDDD' (with hyphen)
        # cc is the country code
        t.kind = TOK.TELNO
        t.val = (telno, cc)
        return t

    @staticmethod
    def Email(t):
        t.kind = TOK.EMAIL
        return t

    @staticmethod
    def Number(t, n, cases=None, genders=None):
        # The cases parameter is a list of possible cases for this number
        # (if it was originally stated in words)
        t.kind = TOK.NUMBER
        t.val = (n, cases, genders)
        return t

    @staticmethod
    def NumberWithLetter(t, n, c):
        t.kind = TOK.NUMWLETTER
        t.val = (n, c)
        return t

    @staticmethod
    def Currency(t, iso, cases=None, genders=None):
        # The cases parameter is a list of possible cases for this currency name
        # (if it was originally stated in words, i.e. not abbreviated)
        t.kind = TOK.CURRENCY
        t.val = (iso, cases, genders)
        return t

    @staticmethod
    def Amount(t, iso, n, cases=None, genders=None):
        # The cases parameter is a list of possible cases for this amount
        # (if it was originally stated in words)
        t.kind = TOK.AMOUNT
        t.val = (n, iso, cases, genders)
        return t

    @staticmethod
    def Percent(t, n, cases=None, genders=None):
        t.kind = TOK.PERCENT
        t.val = (n, cases, genders)
        return t

    @staticmethod
    def Ordinal(t, n):
        t.kind = TOK.ORDINAL
        t.val = n
        return t

    @staticmethod
    def Url(t):
        t.kind = TOK.URL
        return t

    @staticmethod
    def Domain(t):
        t.kind = TOK.DOMAIN
        return t

    @staticmethod
    def Hashtag(t):
        t.kind = TOK.HASHTAG
        return t

    @staticmethod
    def Ssn(t):
        t.kind = TOK.SSN
        return t

    @staticmethod
    def Molecule(t):
        t.kind = TOK.MOLECULE
        return t

    @staticmethod
    def Username(t, username):
        t.kind = TOK.USERNAME
        t.val = username
        return t

    @staticmethod
    def SerialNumber(t):
        t.kind = TOK.SERIALNUMBER
        return t

    @staticmethod
    def Measurement(t, unit, val):
        t.kind = TOK.MEASUREMENT
        t.val = (unit, val)
        return t

    @staticmethod
    def Word(t, m=None):
        # The m parameter is intended for a list of BIN_Meaning tuples
        # fetched from the BÍN database
        t.kind = TOK.WORD
        t.val = m
        return t

    @staticmethod
    def Unknown(t):
        t.kind = TOK.UNKNOWN
        return t

    @staticmethod
    def Person(w, m=None):
        # The m parameter is intended for a list of PersonName tuples:
        # (name, gender, case)
        return Tok(TOK.PERSON, w, m)

    @staticmethod
    def Entity(w):
        return Tok(TOK.ENTITY, w, None)

    @staticmethod
    def Company(w):
        return Tok(TOK.COMPANY, w, None)

    @staticmethod
    def Begin_Paragraph(t):
        t.kind = TOK.P_BEGIN
        return

    @staticmethod
    def End_Paragraph(t):
        t.kind = TOK.P_END
        return t

    @staticmethod
    def Begin_Sentence(num_parses=0, err_index=None):
        return Tok(TOK.S_BEGIN, None, (num_parses, err_index))

    @staticmethod
    def End_Sentence():
        return Tok(TOK.S_END, None, None)

    @staticmethod
    def End_Sentinel():
        return Tok(TOK.X_END, None, None)

    @staticmethod
    def Split_Sentence(t):
        t.kind = TOK.S_SPLIT
        return t


def normalized_text(token):
    """ Returns token text after normalizing punctuation """
    return token.val[1] if token.kind == TOK.PUNCTUATION else token.txt


def text_from_tokens(tokens):
    """ Return text from a list of tokens, without normalization """
    return " ".join(t.txt for t in tokens if t.txt)


def normalized_text_from_tokens(tokens):
    """ Return text from a list of tokens, without normalization """
    return " ".join(filter(None, map(normalized_text, tokens)))


def is_valid_date(y, m, d):
    """ Returns True if y, m, d is a valid date """
    if (1776 <= y <= 2100) and (1 <= m <= 12) and (1 <= d <= DAYS_IN_MONTH[m]):
        try:
            datetime.datetime(year=y, month=m, day=d)
            return True
        except ValueError:
            pass
    return False


def parse_digits(tok, convert_numbers):
    """ Parse a raw token starting with a digit """
    w = tok.txt
    s = re.match(r"\d{1,2}:\d\d:\d\d,\d\d(?!\d)", w)
    if s:
        # Looks like a 24-hour clock with milliseconds, H:M:S:MS
        # TODO use millisecond information in token
        g = s.group()
        p = g.split(":")
        h = int(p[0])
        m = int(p[1])
        sec = int(p[2].split(",")[0])
        if (0 <= h < 24) and (0 <= m < 60) and (0 <= sec < 60):
            t, rest = tok.split(s.end())
            return TOK.Time(t, h, m, sec), rest

    s = re.match(r"\d{1,2}:\d\d:\d\d(?!\d)", w)
    if s:
        # Looks like a 24-hour clock, H:M:S
        g = s.group()
        p = g.split(":")
        h = int(p[0])
        m = int(p[1])
        sec = int(p[2])
        if (0 <= h < 24) and (0 <= m < 60) and (0 <= sec < 60):
            t, rest = tok.split(s.end())
            return TOK.Time(t, h, m, sec), rest

    s = re.match(r"\d{1,2}:\d\d(?!\d)", w)
    if s:
        # Looks like a 24-hour clock, H:M
        g = s.group()
        p = g.split(":")
        h = int(p[0])
        m = int(p[1])
        if (0 <= h < 24) and (0 <= m < 60):
            t, rest = tok.split(s.end())
            return TOK.Time(t, h, m, 0), rest

    s = re.match(r"((\d{4}-\d\d-\d\d)|(\d{4}/\d\d/\d\d))(?!\d)", w)
    if s:
        # Looks like an ISO format date: YYYY-MM-DD or YYYY/MM/DD
        g = s.group()
        if "-" in g:
            p = g.split("-")
        else:
            p = g.split("/")
        y = int(p[0])
        m = int(p[1])
        d = int(p[2])
        if is_valid_date(y, m, d):
            t, rest = tok.split(s.end())
            return TOK.Date(t, y, m, d), rest

    s = (
        re.match(r"\d{1,2}\.\d{1,2}\.\d{2,4}(?!\d)", w)
        or re.match(r"\d{1,2}/\d{1,2}/\d{2,4}(?!\d)", w)
        or re.match(r"\d{1,2}-\d{1,2}-\d{2,4}(?!\d)", w)
    )
    if s:
        # Looks like a date with day, month and year parts
        g = s.group()
        if "/" in g:
            p = g.split("/")
        elif "-" in g:
            p = g.split("-")
        else:
            p = g.split(".")
        y = int(p[2])
        if y <= 99:
            # 50 means 2050, but 51 means 1951
            y += 1900 if y > 50 else 2000
        m = int(p[1])
        d = int(p[0])
        if m > 12 >= d:
            # Probably wrong way (i.e. U.S. American way) around
            m, d = d, m
        if is_valid_date(y, m, d):
            t, rest = tok.split(s.end())
            return TOK.Date(t, y, m, d), rest

    s = re.match(r"(\d{2})\.(\d{2})(?!\d)", w)
    if s:
        # A date in the form dd.mm
        # (Allowing hyphens here would interfere with for instance
        # sports scores and phrases such as 'Það voru 10-12 manns þarna.')
        g = s.group()
        d = int(s.group(1))
        m = int(s.group(2))
        if (1 <= m <= 12) and (1 <= d <= DAYS_IN_MONTH[m]):
            t, rest = tok.split(s.end())
            return TOK.Daterel(t, y=0, m=m, d=d), rest

    s = re.match(r"(\d{2})[-.](\d{4})(?!\d)", w)
    if s:
        # A date in the form of mm.yyyy or mm-yyyy
        g = s.group()
        m = int(s.group(1))
        y = int(s.group(2))
        if (1776 <= y <= 2100) and (1 <= m <= 12):
            t, rest = tok.split(s.end())
            return TOK.Daterel(t, y=y, m=m, d=0), rest

    # Note: the following must use re.UNICODE to make sure that
    # \w matches all Icelandic characters under Python 2
    s = re.match(r"\d+([a-zA-Z])(?!\w)", w, re.UNICODE)
    if s:
        # Looks like a number with a single trailing character, e.g. 14b, 33C, 1122f
        g = s.group()
        c = g[-1:]
        # Only match if the single character is not a
        # unit of measurement (e.g. 'A', 'l', 'V')
        if c not in SI_UNITS_SET:
            n = int(g[:-1])
            t, rest = tok.split(s.end())
            return TOK.NumberWithLetter(t, n, c), rest

    s = NUM_WITH_UNIT_REGEX1.match(w)
    if s:
        # Icelandic-style number followed by an SI unit, or degree/percentage,
        # or currency symbol
        g = s.group()
        val = float(s.group(1).replace(".", "").replace(",", "."))
        unit = s.group(4)
        if unit in CURRENCY_SYMBOLS:
            # This is an amount with a currency symbol at the end
            iso = CURRENCY_SYMBOLS[unit]
            t, rest = tok.split(s.end())
            return TOK.Amount(t, iso, val), rest
        unit, factor = SI_UNITS[unit]
        if callable(factor):
            val = factor(val)
        else:
            # Simple scaling factor
            val *= factor
        if unit in ("%", "‰"):
            t, rest = tok.split(s.end())
            return TOK.Percent(t, val), rest
        t, rest = tok.split(s.end())
        return TOK.Measurement(t, unit, val), rest

    s = NUM_WITH_UNIT_REGEX2.match(w)
    if s:
        # English-style number followed by an SI unit, or degree/percentage,
        # or currency symbol
        g = s.group()
        val = float(s.group(1).replace(",", ""))
        unit = s.group(4)
        if unit in CURRENCY_SYMBOLS:
            # This is an amount with a currency symbol at the end
            iso = CURRENCY_SYMBOLS[unit]
            t, rest = tok.split(s.end())
            return TOK.Amount(t, iso, val), rest
        unit, factor = SI_UNITS[unit]
        if callable(factor):
            val = factor(val)
        else:
            # Simple scaling factor
            val *= factor
        t, rest = tok.split(s.end())
        if convert_numbers:
            t.substitute_all(",", "x")  # Change thousands separator to 'x'
            t.substitute_all(".", ",")  # Change decimal separator to ','
            t.substitute_all("x", ".")  # Change 'x' to '.'
        if unit in ("%", "‰"):
            return TOK.Percent(t, val), rest
        return TOK.Measurement(t, unit, val), rest

    s = NUM_WITH_UNIT_REGEX3.match(w)
    if s:
        # One or more digits, followed by a unicode
        # vulgar fraction char (e.g. '2½') and an SI unit,
        # percent/promille, or currency code
        g = s.group()
        ln = s.group(1)
        vf = s.group(2)
        orig_unit = s.group(3)
        value = float(ln) + unicodedata.numeric(vf)
        if orig_unit in CURRENCY_SYMBOLS:
            # This is an amount with a currency symbol at the end
            iso = CURRENCY_SYMBOLS[orig_unit]
            t, rest = tok.split(s.end())
            return TOK.Amount(t, iso, value), rest
        unit, factor = SI_UNITS[orig_unit]
        if callable(factor):
            value = factor(value)
        else:
            # Simple scaling factor
            value *= factor
        if unit in ("%", "‰"):
            t, rest = tok.split(s.end())
            return TOK.Percent(t, value), rest
        t, rest = tok.split(s.end())
        return TOK.Measurement(t, unit, value), rest

    s = re.match(r"(\d+)([\u00BC-\u00BE\u2150-\u215E])", w, re.UNICODE)
    if s:
        # One or more digits, followed by a unicode vulgar fraction char (e.g. '2½')
        g = s.group()
        ln = s.group(1)
        vf = s.group(2)
        val = float(ln) + unicodedata.numeric(vf)
        t, rest = tok.split(s.end())
        return TOK.Number(t, val), rest

    s = re.match(
        r"[\+\-]?\d+(\.\d\d\d)*,\d+(?!\d*\.\d)", w
    )  # Can't end with digits.digits
    if s:
        # Icelandic-style real number formatted with decimal comma (,)
        # and possibly thousands separators (.)
        # (we need to check this before checking integers)
        g = s.group()
        if re.match(r",\d+", w[len(g) :]):
            # English-style thousand separator multiple times
            s = None
        else:
            n = re.sub(r"\.", "", g)  # Eliminate thousands separators
            n = re.sub(",", ".", n)  # Convert decimal comma to point
            t, rest = tok.split(s.end())
            return TOK.Number(t, float(n)), rest

    s = re.match(r"[\+\-]?\d+(\.\d\d\d)+(?!\d)", w)
    if s:
        # Integer with a '.' thousands separator
        # (we need to check this before checking dd.mm dates)
        g = s.group()
        n = re.sub(r"\.", "", g)  # Eliminate thousands separators
        t, rest = tok.split(s.end())
        return TOK.Number(t, int(n)), rest

    s = re.match(r"\d{1,2}/\d{1,2}(?!\d)", w)
    if s:
        # Looks like a date (and not something like 10/2007)
        g = s.group()
        p = g.split("/")
        m = int(p[1])
        d = int(p[0])
        if (
            p[0][0] != "0"
            and p[1][0] != "0"
            and ((d <= 5 and m <= 6) or (d == 1 and m <= 10))
        ):
            # This is probably a fraction, not a date
            # (1/2, 1/3, 1/4, 1/5, 1/6, 2/3, 2/5, 5/6 etc.)
            # Return a number
            t, rest = tok.split(s.end())
            return TOK.Number(t, float(d) / m), rest
        if m > 12 >= d:
            # Date is probably wrong way around
            m, d = d, m
        if (1 <= m <= 12) and (1 <= d <= DAYS_IN_MONTH[m]):
            # Looks like a (roughly) valid date
            t, rest = tok.split(s.end())
            return TOK.Daterel(t, y=0, m=m, d=d), rest

    s = re.match(r"\d\d\d\d(?!\d)", w)
    if s:
        n = int(s.group())
        if 1776 <= n <= 2100:
            # Looks like a year
            t, rest = tok.split(4)
            return TOK.Year(t, n), rest

    s = re.match(r"\d{6}\-\d{4}(?!\d)", w)
    if s:
        # Looks like a social security number
        g = s.group()
        if valid_ssn(g):
            t, rest = tok.split(11)
            return TOK.Ssn(t), rest

    s = re.match(r"\d\d\d\-\d\d\d\d(?!\d)", w)
    if s and w[0] in TELNO_PREFIXES:
        # Looks like a telephone number
        telno = s.group()
        t, rest = tok.split(8)
        return TOK.Telno(t, telno), rest
    if s:
        # Most likely some sort of serial number
        # Unknown token for now, don't want it separated
        t, rest = tok.split(s.end())
        return TOK.SerialNumber(t), rest

    s = re.match(r"\d+\-\d+(\-\d+)+", w)
    if s:
        # Multi-component serial number
        t, rest = tok.split(s.end())
        return TOK.SerialNumber(t), rest

    s = re.match(r"\d\d\d\d\d\d\d(?!\d)", w)
    if s and w[0] in TELNO_PREFIXES:
        # Looks like a telephone number
        telno = w[0:3] + "-" + w[3:7]
        t, rest = tok.split(7)
        return TOK.Telno(t, telno), rest

    s = re.match(r"\d+\.\d+(\.\d+)+", w)
    if s:
        # Some kind of ordinal chapter number: 2.5.1 etc.
        # (we need to check this before numbers with decimal points)
        g = s.group()
        # !!! TODO: A better solution would be to convert 2.5.1 to (2,5,1)
        n = re.sub(r"\.", "", g)  # Eliminate dots, 2.5.1 -> 251
        t, rest = tok.split(s.end())
        return TOK.Ordinal(t, int(n)), rest

    s = re.match(r"[\+\-]?\d+(,\d\d\d)*\.\d+", w)
    if s:
        # English-style real number with a decimal point (.),
        # and possibly commas as thousands separators (,)
        g = s.group()
        n = re.sub(",", "", g)  # Eliminate thousands separators
        # !!! TODO: May want to mark this as an error
        t, rest = tok.split(s.end())
        if convert_numbers:
            t.substitute_all(",", "x")  # Change thousands separator to 'x'
            t.substitute_all(".", ",")  # Change decimal separator to ','
            t.substitute_all("x", ".")  # Change 'x' to '.'
        return TOK.Number(t, float(n)), rest

    s = re.match(r"[\+\-]?\d+(,\d\d\d)*(?!\d)", w)
    if s:
        # Integer, possibly with a ',' thousands separator
        g = s.group()
        n = re.sub(",", "", g)  # Eliminate thousands separators
        # !!! TODO: May want to mark this as an error
        if convert_numbers:
            t.substitute_all(",", ".")  # Change thousands separator to a dot
        t, rest = tok.split(s.end())
        return TOK.Number(t, int(n)), rest

    # Strange thing
    # !!! TODO: May want to mark this as an error
    return TOK.Unknown(tok), Tok(TOK.RAW, "", None, "", []) # TODO: is this the correct thing for the rest token?


def html_escape(match):
    """ Regex substitution function for HTML escape codes """
    g = match.group(4)
    if g is not None:
        # HTML escape string: 'acute'
        return match.span(), HTML_ESCAPES[g]
    g = match.group(2)
    if g is not None:
        # Hex code: '#xABCD'
        return match.span(), unicode_chr(int(g[2:], base=16))
    g = match.group(3)
    assert g is not None
    # Decimal code: '#8930'
    return match.span(), unicode_chr(int(g[1:]))


def unicode_replacement(token):
    """ Replace some composite glyphs with single code points """
    total_reduction = 0
    for m in UNICODE_REGEX.finditer(token.txt):
        span, new_letter = m.span(), UNICODE_REPLACEMENTS[m.group(0)]
        token.substitute((span[0]-total_reduction, span[1]-total_reduction), new_letter)
        total_reduction += (span[1] - span[0] - len(new_letter))
    return token


def html_replacement(token):
    """ Replace html escape sequences with their proper characters """
    total_reduction = 0
    for m in HTML_ESCAPE_REGEX.finditer(token.txt):
        span, new_letter = html_escape(m)
        token.substitute((span[0]-total_reduction, span[1]-total_reduction), new_letter)
        total_reduction += (span[1] - span[0] - len(new_letter))
    return token


def gen_from_string(txt, replace_composite_glyphs=True, replace_html_escapes=False):
    """ Generate rough tokens from a string """
    # If there are consecutive newlines in the string (i.e. two
    # newlines separated only by whitespace), we interpret
    # them as hard sentence boundaries
    first = True
    for span in re.split(r"\n\s*\n", txt):
        if first:
            first = False
        else:
            # Return a sentence splitting token in lieu of the
            # newline pair that separates the spans
            yield Tok(TOK.S_SPLIT, None, None)

        tok_big = Tok(TOK.RAW, span, None, span, list(range(len(span))))
        if replace_composite_glyphs:
            # Replace composite glyphs with single code points
            tok_big = unicode_replacement(tok_big)
        if replace_html_escapes:
            # Replace HTML escapes: '&aacute;' -> 'á'
            tok_big = html_replacement(tok_big)

        while tok_big.txt != "":
            res = ROUGH_TOKEN_REGEX.match(tok_big.txt)
            tok, tok_big = tok_big.split(res.span(0)[1])

            # Remove whitespace from the start of the token
            tok.substitute(res.span(1), "")
            yield tok


def gen(text_or_gen, replace_composite_glyphs=True, replace_html_escapes=False):
    """ Generate rough tokens from a string or a generator """
    if text_or_gen is None:
        return
    if is_str(text_or_gen):
        # The parameter is a single string: wrap it in an iterable
        text_or_gen = [text_or_gen]
    # Iterate through text_or_gen, which is assumed to yield strings
    saved = None
    for txt in text_or_gen:
        #txt = txt.strip()
        if not txt:
            # Empty line: signal this to the consumer of the generator
            yield Tok(TOK.S_SPLIT, None, None)
        else:
            if saved:
                # There is a remainder from the last token.
                txt = saved + txt
                saved = None
            # Convert to a Unicode string (if Python 2.7)
            txt = make_str(txt)
            # Yield the contained rough tokens
            for t in gen_from_string(
                txt, replace_composite_glyphs, replace_html_escapes
            ):
                if t.txt == "" and t._original != "":
                    # Prevent emitting an empty line signal when there's extra
                    # whitespace at the end of a text segment. Splice it onto
                    # the front of the next one.
                    saved = t._original
                else:
                    yield t


def could_be_end_of_sentence(next_token, test_set=TOK.TEXT, multiplier=False):
    """ Return True if next_token could be ending the current sentence or
        starting the next one """
    return next_token.kind in TOK.END or (
        # Check whether the next token is an uppercase word, except if
        # it is a month name (frequently misspelled in uppercase) or
        # roman numeral, or a currency abbreviation if preceded by a
        # multiplier (for example þ. USD for thousands of USD)
        next_token.kind in test_set
        and next_token.txt[0].isupper()
        and next_token.txt.lower() not in MONTHS
        and not RE_ROMAN_NUMERAL.match(next_token.txt)
        and not (next_token.txt in CURRENCY_ABBREV and multiplier)
    )


def parse_tokens(txt, **options):
    """ Generator that parses contiguous text into a stream of tokens """

    # Obtain individual flags from the options dict
    convert_numbers = options.get("convert_numbers", False)
    replace_composite_glyphs = options.get("replace_composite_glyphs", True)
    replace_html_escapes = options.get("replace_html_escapes", False)

    # The default behavior for kludgy ordinals is to pass them
    # through as word tokens
    handle_kludgy_ordinals = options.get(
        "handle_kludgy_ordinals", KLUDGY_ORDINALS_PASS_THROUGH
    )

    # This code proceeds roughly as follows:
    # 1) The text is split into raw tokens on whitespace boundaries.
    # 2) (By far the most common case:) Raw tokens that are purely
    #    alphabetic are yielded as word tokens.
    # 3) Punctuation from the front of the remaining raw token is identified
    #    and yielded. A special case applies for quotes.
    # 4) A set of checks is applied to the rest of the raw token, identifying
    #    tokens such as e-mail addresses, domains and @usernames. These can
    #    start with digits, so the checks must occur before step 5.
    # 5) Tokens starting with a digit (eventually preceded
    #    by a + or - sign) are sent off to a separate function that identifies
    #    integers, real numbers, dates, telephone numbers, etc. via regexes.
    # 6) After such checks, alphabetic sequences (words) at the start of the
    #    raw token are identified. Such a sequence can, by the way, also
    #    contain embedded apostrophes and hyphens (Dunkin' Donuts, Mary's,
    #    marg-ítrekaðri).
    # 7) The process is repeated from step 4) until the current raw token is
    #    exhausted. At that point, we obtain the next token and start from 2).

    for rt in gen(txt, replace_composite_glyphs, replace_html_escapes):
        # rt: raw token

        # Handle each sequence w of non-whitespace characters

        if not rt.txt:
            # An empty string signals an empty line, which splits sentences
            yield TOK.Split_Sentence(rt)
            continue

        if rt.txt.isalpha() or rt.txt in SI_UNITS:
            # Shortcut for most common case: pure word
            yield TOK.Word(rt)
            continue

        if len(rt.txt) > 1:
            if rt.txt[0] in SIGN_PREFIX and rt.txt[1] in DIGITS_PREFIX:
                # Digit, preceded by sign (+/-): parse as a number
                # Note that we can't immediately parse a non-signed number
                # here since kludges such as '3ja' and domain names such as '4chan.com'
                # need to be handled separately below
                t, rt = parse_digits(rt, convert_numbers)
                yield t
                if not rt.txt:
                    continue
            elif rt.txt[0] in COMPOSITE_HYPHENS and rt.txt[1].isalpha():
                # This may be something like '-menn' in 'þingkonur og -menn'
                i = 2
                while i < len(rt.txt) and rt.txt[i].isalpha():
                    i += 1
                # We allow -menn and -MENN, but not -Menn or -mEnn
                # We don't allow -Á or -Í, i.e. single-letter uppercase combos
                if rt.txt[:i].islower() or (i > 2 and rt.txt[:i].isupper()):
                    head, rt = rt.split(i)
                    yield TOK.Word(head)

        # Shortcut for quotes around a single word
        if len(rt.txt) >= 3:
            if rt.txt[0] in DQUOTES and rt.txt[-1] in DQUOTES:
                # Convert to matching Icelandic quotes
                # yield TOK.Punctuation("„")
                if rt.txt[1:-1].isalpha():
                    first_punct, rt = rt.split(1)
                    word, last_punct = rt.split(-1)
                    yield TOK.Punctuation(first_punct, normalized="„")
                    yield TOK.Word(word)
                    yield TOK.Punctuation(last_punct, normalized="“")
                    #yield TOK.Punctuation(w[0], normalized="„")
                    #yield TOK.Word(w[1:-1])
                    #yield TOK.Punctuation(w[-1], normalized="“")
                    continue
            elif rt.txt[0] in SQUOTES and rt.txt[-1] in SQUOTES:
                # Convert to matching Icelandic quotes
                # yield TOK.Punctuation("‚")
                if rt.txt[1:-1].isalpha():
                    first_punct, rt = rt.split(1)
                    word, last_punct = rt.split(-1)
                    yield TOK.Punctuation(first_punct, normalized="‚")
                    yield TOK.Word(word)
                    yield TOK.Punctuation(last_punct, normalized="‘")
                    #yield TOK.Punctuation(w[0], normalized="‚")
                    #yield TOK.Word(w[1:-1])
                    #yield TOK.Punctuation(w[-1], normalized="‘")
                    continue

        # Special case for leading quotes, which are interpreted
        # as opening quotes
        if len(rt.txt) > 1:
            if rt.txt[0] in DQUOTES:
                # Convert simple quotes to proper opening quotes
                punct, rt = rt.split(1)
                yield TOK.Punctuation(punct, normalized="„")
            elif rt.txt[0] in SQUOTES:
                # Convert simple quotes to proper opening quotes
                punct, rt = rt.split(1)
                yield TOK.Punctuation(punct, normalized="‚")

        # More complex case of mixed punctuation, letters and numbers
        while rt.txt:
            # Handle punctuation
            ate = False
            while rt.txt and rt.txt[0] in PUNCTUATION:
                ate = True
                lw = len(rt.txt)
                if rt.txt.startswith("[...]"):
                    punct, rt = rt.split(5)
                    yield TOK.Punctuation(punct, normalized="[…]")
                elif rt.txt.startswith("[…]"):
                    punct, rt = rt.split(3)
                    yield TOK.Punctuation(punct)
                elif rt.txt.startswith("..."):
                    # Treat ellipsis as one piece of punctuation
                    numdots = 0
                    for c in rt.txt:
                        if c == '.':
                            numdots += 1
                        else:
                            break
                    dots, rt = rt.split(numdots)
                    yield TOK.Punctuation(dots, normalized="…")
                elif rt.txt.startswith("…"):
                    # Treat ellipsis as one piece of punctuation
                    numdots = 0
                    for c in rt.txt:
                        if c == '…':
                            numdots += 1
                        else:
                            break
                    dots, rt = rt.split(numdots)
                    yield TOK.Punctuation(dots, normalized="…")
                    # TODO LAGA Hér ætti að safna áfram.
                # TODO Was at the end of a word or by itself, should be ",".
                # Won't correct automatically, check for M6
                elif rt.txt == ",,":
                    punct, rt = rt.split(2)
                    yield TOK.Punctuation(punct, normalized=",")
                # TODO STILLING kommum í upphafi orðs breytt í gæsalappir
                elif rt.txt.startswith(",,"):
                    # Probably an idiot trying to type opening double quotes with commas
                    punct, rt = rt.split(2)
                    yield TOK.Punctuation(punct, normalized="„")
                elif lw == 2 and (rt.txt == "[[" or rt.txt == "]]"):
                    # Begin or end paragraph marker
                    marker, rt = rt.split(2)
                    if rt.txt == "[[":
                        yield TOK.Begin_Paragraph(marker)
                    else:
                        yield TOK.End_Paragraph(marker)
                elif rt.txt[0] in HYPHENS:
                    # Normalize all hyphens the same way
                    punct, rt = rt.split(1)
                    yield TOK.Punctuation(punct, normalized=HYPHEN)
                elif rt.txt[0] in DQUOTES:
                    # Convert to a proper closing double quote
                    punct, rt = rt.split(1)
                    yield TOK.Punctuation(punct, normalized="“")
                elif rt.txt[0] in SQUOTES:
                    # Left with a single quote, convert to proper closing quote
                    punct, rt = rt.split(1)
                    yield TOK.Punctuation(punct, normalized="‘")
                elif lw > 1 and rt.txt.startswith("#"):
                    # Might be a hashtag, processed later
                    ate = False
                    break
                elif lw > 1 and rt.txt.startswith("@"):
                    # Username on Twitter or other social media platforms
                    s = re.match(r"\@[0-9a-z_]+", rt.txt)
                    if s:
                        g = s.group()
                        username, rt = rt.split(s.end())
                        yield TOK.Username(username, g[1:])
                    else:
                        punct, rt = rt.split(1)
                        yield TOK.Punctuation(punct)
                else:
                    punct, rt = rt.split(1)
                    yield TOK.Punctuation(punct)

            # End of punctuation loop
            # Check for specific token types other than punctuation

            if rt.txt and "@" in rt.txt:
                # Check for valid e-mail
                # Note: we don't allow double quotes (simple or closing ones) in e-mails here
                # even though they're technically allowed according to the RFCs
                s = re.match(r"[^@\s]+@[^@\s]+(\.[^@\s\.,/:;\"\(\)%#!\?”]+)+", rt.txt)
                if s:
                    ate = True
                    email, rt = rt.split(s.end())
                    yield TOK.Email(email)

            # Unicode single-char vulgar fractions
            # TODO: Support multiple-char unicode fractions that
            # use super/subscript w. DIVISION SLASH (U+2215)
            if rt.txt and rt.txt[0] in SINGLECHAR_FRACTIONS:
                ate = True
                num, rt = rt.split(1)
                yield TOK.Number(num, unicodedata.numeric(num.txt[0]))

            if rt.txt and rt.txt.startswith(URL_PREFIXES):
                # Handle URL: cut RIGHT_PUNCTUATION characters off its end,
                # even though many of them are actually allowed according to
                # the IETF RFC
                endp = ""
                w = rt.txt
                while w and w[-1] in RIGHT_PUNCTUATION:
                    endp = w[-1] + endp
                    w = w[:-1]
                url, rt = rt.split(len(w))
                yield TOK.Url(url)
                ate = True

            if rt.txt and len(rt.txt) >= 2 and re.match(r"#\w", rt.txt, re.UNICODE):
                # Handle hashtags. Eat all text up to next punctuation character
                # so we can handle strings like "#MeToo-hreyfingin" as two words
                w = rt.txt
                tag = w[:1]
                w = w[1:]
                while w and w[0] not in PUNCTUATION:
                    tag += w[0]
                    w = w[1:]
                tag_tok, rt = rt.split(len(tag))
                if re.match(r"#\d+$", tag):
                    # Hash is being used as a number sign, e.g. "#12"
                    yield TOK.Ordinal(tag_tok, int(tag[1:]))
                else:
                    yield TOK.Hashtag(tag_tok)
                ate = True

            # Domain name (e.g. greynir.is)
            if (
                rt.txt
                and len(rt.txt) >= MIN_DOMAIN_LENGTH
                and rt.txt[0].isalnum()  # All domains start with an alphanumeric char
                and "." in rt.txt[1:-2]  # Optimization, TLD is at least 2 chars
                and DOMAIN_REGEX.search(rt.txt)
            ):
                w = rt.txt
                endp = ""
                while w and w[-1] in PUNCTUATION:
                    endp = w[-1] + endp
                    w = w[:-1]
                domain, rt = rt.split(len(w))
                yield TOK.Domain(domain)
                ate = True

            # Numbers or other stuff starting with a digit
            # (eventually prefixed by a '+' or '-')
            if rt.txt and (
                rt.txt[0] in DIGITS_PREFIX
                or (rt.txt[0] in SIGN_PREFIX and len(rt.txt) >= 2 and rt.txt[1] in DIGITS_PREFIX)
            ):
                # Handle kludgy ordinals: '3ji', '5ti', etc.
                for key, val in items(ORDINAL_ERRORS):
                    if rt.txt.startswith(key):
                        # This is a kludgy ordinal
                        key_tok, rt = rt.split(len(key))
                        if handle_kludgy_ordinals == KLUDGY_ORDINALS_MODIFY:
                            # XXX TODO: We currently fail origin tracking in this case since the Tok class isn't 
                            #           set up to handle substitutions that lengthen the string.
                            # Convert ordinals to corresponding word tokens:
                            # '1sti' -> 'fyrsti', '3ji' -> 'þriðji', etc.
                            #yield TOK.Word(val)
                            yield Tok(TOK.WORD, val, None)
                        elif (
                            handle_kludgy_ordinals == KLUDGY_ORDINALS_TRANSLATE
                            and key in ORDINAL_NUMBERS
                        ):
                            # Convert word-form ordinals into ordinal tokens,
                            # i.e. '1sti' -> TOK.Ordinal('1sti', 1),
                            # but leave other kludgy constructs ('2ja')
                            # as word tokens
                            yield TOK.Ordinal(key_tok, ORDINAL_NUMBERS[key])
                        else:
                            # No special handling of kludgy ordinals:
                            # yield them unchanged as word tokens
                            yield TOK.Word(key_tok)
                        break  # This skips the for loop 'else'
                else:
                    # Not a kludgy ordinal: eat tokens starting with a digit
                    t, rt = parse_digits(rt, convert_numbers)
                    yield t
                # Continue where the digits parser left off
                ate = True

                if rt.txt:
                    # Check for an SI unit immediately following a number
                    r = SI_UNITS_REGEX.match(rt.txt)
                    if r:
                        # Handle the case where a measurement unit is
                        # immediately following a number, without an intervening space
                        # (note that some of them contain nonalphabetic characters,
                        # so they won't be caught by the isalpha() check below)
                        unit, rt = rt.split(r.end())
                        yield TOK.Word(unit)

            # Check for molecular formula ('H2SO4')
            if rt.txt:
                r = MOLECULE_REGEX.match(rt.txt)
                if r is not None:
                    g = r.group()
                    if g not in Abbreviations.DICT and MOLECULE_FILTER.search(g):
                        # Correct format, containing at least one digit
                        # and not separately defined as an abbreviation:
                        # We assume that this is a molecular formula
                        molecule, rt = rt.split(r.end())
                        yield TOK.Molecule(molecule)
                        ate = True

            # Check for currency abbreviations immediately followed by a number
            if rt.txt and len(rt.txt) > 3 and rt.txt[0:3] in CURRENCY_ABBREV and rt.txt[3].isdigit():
                # XXX: This feels a little hacky
                temp_tok = Tok(TOK.RAW, rt.txt[3:], None)
                digit_tok, rest = parse_digits(temp_tok, convert_numbers)
                if digit_tok.kind == TOK.NUMBER:
                    amount, rt = rt.split(3+len(digit_tok.txt))
                    yield TOK.Amount(amount, amount.txt[:3], digit_tok.val[0])
                    ate = True

            # Alphabetic characters
            # (or a hyphen immediately followed by alphabetic characters,
            # such as in 'þingkonur og -menn')
            if rt.txt and rt.txt[0].isalpha(): # XXX: This does not seem to fit the comment above ('-'.isalpha()==False)
                ate = True
                lw = len(rt.txt)
                i = 1
                while i < lw and (
                    rt.txt[i].isalpha()
                    or (rt.txt[i] in PUNCT_INSIDE_WORD and i + 1 < lw and rt.txt[i + 1].isalpha())
                ):
                    # We allow dots to occur inside words in the case of
                    # abbreviations; also apostrophes are allowed within
                    # words and at the end (albeit not consecutively)
                    # (O'Malley, Mary's, it's, childrens', O‘Donnell).
                    # The same goes for ² and ³
                    i += 1
                if i < lw and rt.txt[i] in PUNCT_ENDING_WORD:
                    i += 1
                # Make a special check for the occasional erroneous source text
                # case where sentences run together over a period without a space:
                # 'sjávarútvegi.Það'
                # TODO STILLING Viljum merkja sem villu fyrir málrýni, og hafa
                # sem mögulega stillingu.
                ww = rt.txt[0:i]
                a = ww.split(".")
                if (
                    len(a) == 2
                    # First part must be more than one letter for us to split
                    and len(a[0]) > 1
                    # The first part may start with an uppercase or lowercase letter
                    # but the rest of it must be lowercase
                    and a[0][1:].islower()
                    and a[1]
                    # The second part must start with an uppercase letter
                    and a[1][0].isupper()
                    # Corner case: an abbrev such as 'f.Kr' should not be split
                    and rt.txt[0 : i + 1] not in Abbreviations.DICT
                ):
                    # We have a lowercase word immediately followed by a period
                    # and an uppercase word
                    word1, rt = rt.split(len(a[0]))
                    punct, rt = rt.split(1)
                    word2, rt = rt.split(len(a[1]))
                    yield TOK.Word(word1)
                    yield TOK.Punctuation(punct)
                    yield TOK.Word(word2)
                    #yield TOK.Word(a[0])
                    #yield TOK.Punctuation(".")
                    #yield TOK.Word(a[1])
                else:
                    if ww.endswith("-og") or ww.endswith("-eða"):
                        # Handle missing space before 'og'/'eða',
                        # such as 'fjármála-og efnahagsráðuneyti'
                        a = ww.split("-")

                        word1, rt = rt.split(len(a[0]))
                        punct, rt = rt.split(1)
                        word2, rt = rt.split(len(a[1]))
                        yield TOK.Word(word1)
                        yield TOK.Punctuation(punct, normalized=COMPOSITE_HYPHEN)
                        yield TOK.Word(word2)

                        #yield TOK.Word(a[0])
                        #yield TOK.Punctuation("-", normalized=COMPOSITE_HYPHEN)
                        #yield TOK.Word(a[1])
                    else:
                        word, rt = rt.split(i)
                        yield TOK.Word(word)

                if rt.txt and rt.txt[0] in COMPOSITE_HYPHENS:
                    # This is a hyphen or en dash directly appended to a word:
                    # might be a continuation ('fjármála- og efnahagsráðuneyti')
                    # Yield a special hyphen as a marker
                    punct, rt = rt.split(1)
                    yield TOK.Punctuation(punct, normalized=COMPOSITE_HYPHEN)

            # Special case for quotes attached on the right hand side to other stuff,
            # assumed to be closing quotes rather than opening ones
            if rt.txt:
                if rt.txt[0] in SQUOTES:
                    punct, rt = rt.split(1)
                    yield TOK.Punctuation(punct, normalized="‘")
                    ate = True
                elif rt.txt[0] in DQUOTES:
                    punct, rt = rt.split(1)
                    yield TOK.Punctuation(punct, normalized="“")
                    ate = True

            if not ate:
                # Ensure that we eat everything, even unknown stuff
                unk, rt = rt.split(1)
                yield TOK.Unknown(unk)

    # Yield a sentinel token at the end that will be cut off by the final generator
    yield TOK.End_Sentinel()


def parse_particles(token_stream, **options):
    """ Parse a stream of tokens looking for 'particles'
        (simple token pairs and abbreviations) and making substitutions """

    convert_measurements = options.pop("convert_measurements", False)

    def is_abbr_with_period(txt):
        """ Return True if the given token text is an abbreviation
            when followed by a period """
        if "." in txt:
            # There is already a period in it: must be an abbreviation
            # (this applies for instance to "t.d" but not to "mbl.is")
            return True
        if txt in Abbreviations.SINGLES:
            # The token's literal text is defined as an abbreviation
            # followed by a single period
            return True
        if txt.lower() in Abbreviations.SINGLES:
            # The token is in upper or mixed case:
            # We allow it as an abbreviation unless the exact form
            # (most often uppercase) is an abbreviation that doesn't
            # require a period (i.e. isn't in SINGLES).
            # This applies for instance to DR which means
            # "Danmark's Radio" instead of "doktor" (dr.)
            return txt not in Abbreviations.DICT
        return False

    def lookup(abbrev):
        """ Look up an abbreviation, both in original case and in lower case,
            and return either None if not found or a meaning list having one entry """
        m = Abbreviations.DICT.get(abbrev)
        if not m:
            m = Abbreviations.DICT.get(abbrev.lower())
        return list(m) if m else None

    token = None
    try:
        # Maintain a one-token lookahead
        token = next(token_stream)
        while True:
            next_token = next(token_stream)
            # Make the lookahead checks we're interested in
            # Check for currency symbol followed by number, e.g. $10
            if token.txt in CURRENCY_SYMBOLS:
                for symbol, currabbr in items(CURRENCY_SYMBOLS):
                    if (
                        token.kind == TOK.PUNCTUATION # XXX: this should probably be outside the loop
                        and token.txt == symbol
                        and next_token.kind == TOK.NUMBER # XXX: this also
                    ):
                        token = TOK.Amount(
                            token.concatenate(next_token), currabbr, next_token.val[0]
                        )
                        next_token = next(token_stream)
                        break

            # Special case for a DATEREL token of the form "25.10.",
            # i.e. with a trailing period: It can end a sentence
            if token.kind == TOK.DATEREL and "." in token.txt:
                if next_token.txt == ".":
                    next_next_token = next(token_stream)
                    if could_be_end_of_sentence(next_next_token):
                        # This is something like 'Ég fæddist 25.9. Það var gaman.'
                        yield token
                        token = next_token
                    else:
                        # This is something like 'Ég fæddist 25.9. í Svarfaðardal.'
                        y, m, d = token.val
                        token = TOK.Daterel(token.concatenate(next_token), y, m, d)
                    next_token = next_next_token

            # Coalesce abbreviations ending with a period into a single
            # abbreviation token
            if next_token.kind == TOK.PUNCTUATION and next_token.val[1] == ".":
                if (
                    token.kind == TOK.WORD
                    and token.txt[-1] != "."
                    and is_abbr_with_period(token.txt)
                ):
                    # Abbreviation ending with period: make a special token for it
                    # and advance the input stream
                    follow_token = next(token_stream)
                    abbrev = token.txt + "."

                    # Check whether we might be at the end of a sentence, i.e.
                    # the following token is an end-of-sentence or end-of-paragraph,
                    # or uppercase (and not a month name misspelled in upper case).

                    if abbrev in Abbreviations.NAME_FINISHERS:
                        # For name finishers (such as 'próf.') we don't consider a
                        # following person name as an indicator of an end-of-sentence
                        # !!! TODO: This does not work as intended because person names
                        # !!! have not been recognized at this phase in the token pipeline.
                        test_set = TOK.TEXT_EXCL_PERSON
                    else:
                        test_set = TOK.TEXT

                    # TODO STILLING í MONTHS eru einhverjar villur eins og "septembers",
                    # þær þarf að vera hægt að sameina í þessa flóknari tóka en viljum
                    # geta merkt það sem villu. Ætti líklega að setja í sérlista,
                    # WRONG_MONTHS, og sérif-lykkju og setja inn villu í tókann.
                    finish = could_be_end_of_sentence(
                        follow_token, test_set, abbrev in MULTIPLIERS
                    )
                    if finish:
                        # Potentially at the end of a sentence
                        if abbrev in Abbreviations.FINISHERS:
                            # We see this as an abbreviation even if the next sentence
                            # seems to be starting just after it.
                            # Yield the abbreviation without a trailing dot,
                            # and then an 'extra' period token to end the current sentence.
                            token = TOK.Word(token, lookup(abbrev))
                            yield token
                            # Set token to the period
                            token = next_token
                        elif (
                            abbrev in Abbreviations.NOT_FINISHERS
                            or abbrev.lower() in Abbreviations.NOT_FINISHERS
                        ):
                            # This is a potential abbreviation that we don't interpret
                            # as such if it's at the end of a sentence
                            # ('dags.', 'próf.', 'mín.'). Note that this also
                            # applies for uppercase versions: 'Örn.', 'Próf.'
                            yield token
                            token = next_token
                        else:
                            # Substitute the abbreviation and eat the period
                            token = TOK.Word(token.concatenate(next_token), lookup(abbrev))
                    else:
                        # 'Regular' abbreviation in the middle of a sentence:
                        # Eat the period and yield the abbreviation as a single token
                        token = TOK.Word(token.concatenate(next_token), lookup(abbrev))

                    next_token = follow_token

            # Coalesce 'klukkan'/[kl.] + time or number into a time
            if next_token.kind == TOK.TIME or next_token.kind == TOK.NUMBER:
                if token.kind == TOK.WORD and token.txt.lower() in CLOCK_ABBREVS:
                    # Match: coalesce and step to next token
                    if next_token.kind == TOK.NUMBER:
                        # next_token.txt may be a real number, i.e. 13,40,
                        # which may have been converted from 13.40
                        # If we now have hh.mm, parse it as such
                        a = "{0:.2f}".format(next_token.val[0]).split(".")
                        h, m = int(a[0]), int(a[1])
                        token = TOK.Time(token.concatenate(next_token, separator=" "), h, m, 0)
                    else:
                        # next_token.kind is TOK.TIME
                        token = TOK.Time(
                            token.concatenate(next_token, separator=" "),
                            next_token.val[0],
                            next_token.val[1],
                            next_token.val[2],
                        )
                    next_token = next(token_stream)

            # Coalesce 'klukkan/kl. átta/hálfátta' into a time
            elif (
                next_token.kind == TOK.WORD and next_token.txt.lower() in CLOCK_NUMBERS
            ):
                if token.kind == TOK.WORD and token.txt.lower() in CLOCK_ABBREVS:
                    # Match: coalesce and step to next token
                    token = TOK.Time(
                        token.concatenate(next_token, separator=" "),
                        *CLOCK_NUMBERS[next_token.txt.lower()]
                    )
                    next_token = next(token_stream)

            # Coalesce 'klukkan/kl. hálf átta' into a time
            elif next_token.kind == TOK.WORD and next_token.txt.lower() == "hálf":
                if token.kind == TOK.WORD and token.txt.lower() in CLOCK_ABBREVS:
                    time_token = next(token_stream)
                    time_txt = time_token.txt.lower() if time_token.txt else ""
                    if time_txt in CLOCK_NUMBERS and not time_txt.startswith("hálf"):
                        # Match
                        temp_tok = token.concatenate(next_token, separator=" ")
                        temp_tok = temp_tok.concatenate(time_token, separator=" ")
                        token = TOK.Time(
                            temp_tok,
                            *CLOCK_NUMBERS["hálf" + time_txt]
                        )
                        next_token = next(token_stream)
                    else:
                        # Not a match: must retreat
                        yield token
                        token = next_token
                        next_token = time_token

            # Words like 'hálftólf' are only used in temporal expressions
            # so can stand alone
            if token.txt in CLOCK_HALF:
                token = TOK.Time(token, *CLOCK_NUMBERS[token.txt])

            # Coalesce 'árið' + [year|number] into year
            if (token.kind == TOK.WORD and token.txt.lower() in YEAR_WORD) and (
                next_token.kind == TOK.YEAR or next_token.kind == TOK.NUMBER
            ):
                token = TOK.Year(
                    token.concatenate(next_token, separator=" "),
                    next_token.val
                    if next_token.kind == TOK.YEAR
                    else next_token.val[0],
                )
                next_token = next(token_stream)

            # Coalesece 3-digit number followed by 4-digit number into tel. no.
            if (
                token.kind == TOK.NUMBER
                and (next_token.kind == TOK.NUMBER or next_token.kind == TOK.YEAR)
                and token.txt[0] in TELNO_PREFIXES
                and re.search(r"^\d\d\d$", token.txt)
                and re.search(r"^\d\d\d\d$", next_token.txt)
            ):
                telno = token.txt + "-" + next_token.txt
                token = TOK.Telno(token.concatenate(next_token, separator=" "), telno)
                next_token = next(token_stream)

            # Coalesce percentages or promilles into a single token
            if next_token.kind == TOK.PUNCTUATION and next_token.val[1] in ("%", "‰"):
                if token.kind == TOK.NUMBER:
                    # Percentage: convert to a single 'tight' percentage token
                    # In this case, there are no cases and no gender
                    sign = next_token.txt
                    # Store promille as one-tenth of a percentage
                    factor = 1.0 if sign == "%" else 0.1
                    token = TOK.Percent(token.concatenate(next_token), token.val[0] * factor)
                    next_token = next(token_stream)

            # Coalesce ordinals (1. = first, 2. = second...) into a single token
            if next_token.kind == TOK.PUNCTUATION and next_token.val[1] == ".":
                if (
                    token.kind == TOK.NUMBER
                    and not ("." in token.txt or "," in token.txt)
                ) or (
                    token.kind == TOK.WORD
                    and RE_ROMAN_NUMERAL.match(token.txt)
                    # Don't interpret a known abbreviation as a Roman numeral,
                    # for instance the newspaper 'DV'
                    and token.txt not in Abbreviations.DICT
                ):
                    # Ordinal, i.e. whole number or Roman numeral followed by period:
                    # convert to an ordinal token
                    follow_token = next(token_stream)
                    if (
                        follow_token.kind in TOK.END
                        or (
                            follow_token.kind == TOK.PUNCTUATION
                            and follow_token.val[1] in {"„", '"'}
                        )
                        or (
                            follow_token.kind == TOK.WORD
                            and follow_token.txt[0].isupper()
                            and month_for_token(follow_token, True) is None
                        )
                    ):
                        # Next token is a sentence or paragraph end, or opening quotes,
                        # or an uppercase word (and not a month name misspelled in
                        # upper case): fall back from assuming that this is an ordinal
                        yield token  # Yield the number or Roman numeral
                        token = next_token  # The period
                        # The following (uppercase) word or sentence end
                        next_token = follow_token
                    else:
                        # OK: replace the number/Roman numeral and the period
                        # with an ordinal token
                        num = (
                            token.val[0]
                            if token.kind == TOK.NUMBER
                            else roman_to_int(token.txt)
                        )
                        token = TOK.Ordinal(token.concatenate(next_token), num)
                        # Continue with the following word
                        next_token = follow_token

            # Convert "1920 mm" or "30 °C" to a single measurement token
            if (
                token.kind == TOK.NUMBER or token.kind == TOK.YEAR
            ) and next_token.txt in SI_UNITS:

                value = token.val[0] if token.kind == TOK.NUMBER else token.val
                orig_unit = next_token.txt
                unit, factor = SI_UNITS[orig_unit]
                if callable(factor):
                    # We have a lambda conversion function
                    value = factor(value)  # pylint: disable=not-callable
                else:
                    # Simple scaling factor
                    value *= factor
                if unit in ("%", "‰"):
                    token = TOK.Percent(token.concatenate(next_token, separator=" "), value)
                else:
                    token = TOK.Measurement(
                        token.concatenate(next_token, separator=" "), unit, value
                    )
                next_token = next(token_stream)

                # Special case for km/klst.
                if (
                    token.kind == TOK.MEASUREMENT
                    and orig_unit == "km"
                    and next_token.txt == "/"
                ):
                    slashtok = next_token
                    next_token = next(token_stream)
                    if next_token.txt == "klst":
                        unit = token.txt + "/" + next_token.txt
                        temp_tok = token.concatenate(slashtok)
                        temp_tok = temp_tok.concatenate(next_token)
                        token = TOK.Measurement(temp_tok, unit, value)
                        # Eat extra unit
                        next_token = next(token_stream)
                    else:
                        yield token
                        token = slashtok

            if (
                token.kind == TOK.MEASUREMENT
                and token.val[0] == "°"
                and next_token.kind == TOK.WORD
                and next_token.txt in {"C", "F", "K"}
            ):
                # Handle 200° C
                new_unit = "°" + next_token.txt
                unit, factor = SI_UNITS[new_unit]
                if callable(factor):
                    val = factor(token.val[1])
                else:
                    val = factor * token.val[1]

                if convert_measurements:
                    token = TOK.Measurement(
                        # XXX: This is not currently well supported for origin tracking.
                        Tok(TOK.RAW, token.txt[:-1] + " " + new_unit, None),  # 200 °C
                        unit,  # K
                        val,  # 200 converted to Kelvin
                    )
                else:
                    token = TOK.Measurement(
                        token.concatenate(next_token, separator=" "),  # 200° C
                        unit,  # K
                        val,  # 200 converted to Kelvin
                    )

                next_token = next(token_stream)

            # Special case for measurement abbreviations
            # erroneously ending with a period.
            # We only allow this for measurements that end with
            # an alphabetic character, i.e. not for ², ³, °, %, ‰.
            # [ Uncomment the last condition for this behavior:
            # We don't do this for measurement units which
            # have other meanings - such as 'gr' (grams), as
            # 'gr.' is probably the abbreviation for 'grein'. ]
            if (
                token.kind == TOK.MEASUREMENT
                and next_token.kind == TOK.PUNCTUATION
                and next_token.txt == "."
                and token.txt[-1].isalpha()
                # and token.txt.split()[-1] + "." not in Abbreviations.DICT
            ):
                puncttoken = next_token
                next_token = next(token_stream)
                if could_be_end_of_sentence(next_token):
                    # We are at the end of the current sentence; back up
                    yield token
                    token = puncttoken
                else:
                    unit, value = token.val
                    # Add the period to the token text
                    token = TOK.Measurement(token.concatenate(puncttoken), unit, value)

            # Cases such as USD. 44
            if (
                token.txt in CURRENCY_ABBREV
                and next_token.kind == TOK.PUNCTUATION
                and next_token.txt == "."
            ):
                puncttoken = next_token
                next_token = next(token_stream)
                if could_be_end_of_sentence(next_token):
                    # We are at the end of the current sentence; back up
                    yield token
                    token = puncttoken
                else:
                    token = TOK.Currency(token.concatenate(puncttoken), token.txt)

            # Cases such as 19 $, 199.99 $
            if (
                token.kind == TOK.NUMBER
                and next_token.kind == TOK.PUNCTUATION
                and next_token.txt in CURRENCY_SYMBOLS
            ):
                token = TOK.Amount(
                    token.concatenate(next_token, separator=" "),
                    CURRENCY_SYMBOLS[next_token.txt],
                    token.val[0],
                )
                next_token = next(token_stream)

            # Replace straight abbreviations
            # (i.e. those that don't end with a period)
            if token.kind == TOK.WORD and token.val is None:
                if Abbreviations.has_meaning(token.txt):
                    # Add a meaning to the token
                    token = TOK.Word(token, Abbreviations.get_meaning(token.txt))

            # Yield the current token and advance to the lookahead
            yield token
            token = next_token

    except StopIteration:
        # Final token (previous lookahead)
        if token:
            yield token


def parse_sentences(token_stream):
    """ Parse a stream of tokens looking for sentences, i.e. substreams within
        blocks delimited by sentence finishers (periods, question marks,
        exclamation marks, etc.) """

    in_sentence = False
    token = None
    tok_begin_sentence = TOK.Begin_Sentence()
    tok_end_sentence = TOK.End_Sentence()

    try:

        # Maintain a one-token lookahead
        token = next(token_stream)
        while True:
            next_token = next(token_stream)
            if token.kind == TOK.P_BEGIN or token.kind == TOK.P_END:
                # Block start or end: finish the current sentence, if any
                if in_sentence:
                    # If there's whitespace (or something else) hanging on token,
                    # then move it to the end of sentence token.
                    yield tok_end_sentence
                    in_sentence = False
                if token.kind == TOK.P_BEGIN and next_token.kind == TOK.P_END:
                    # P_BEGIN immediately followed by P_END: skip both and continue
                    # The double assignment to token is necessary to ensure that
                    # we are in a correct state if next() raises StopIteration
                    # XXX: We lose origin tracking here!
                    token = None
                    token = next(token_stream)
                    continue
            elif token.kind == TOK.X_END:
                assert not in_sentence
            elif token.kind == TOK.S_SPLIT:
                # Empty line in input: make sure to finish the current
                # sentence, if any, even if no ending punctuation has
                # been encountered
                if in_sentence:
                    yield tok_end_sentence
                in_sentence = False
                # Swallow the S_SPLIT token
                # XXX: We lose origin tracking here!
                token = next_token
                continue
            else:
                if not in_sentence:
                    # This token starts a new sentence
                    yield tok_begin_sentence
                    in_sentence = True
                if (
                    token.kind == TOK.PUNCTUATION
                    and token.val[1] in END_OF_SENTENCE
                    and not (
                        token.val[1]
                        == "…"  # Excluding sentences with ellipsis in the middle
                        and not could_be_end_of_sentence(next_token)
                    )
                ):
                    # Combining punctuation ('??!!!')
                    while (
                        token.val[1] in PUNCT_COMBINATIONS
                        and next_token.txt in PUNCT_COMBINATIONS
                    ):
                        # The normalized form comes from the first token except with "…?"
                        v = token.val[1]
                        if token.val[1] == "…" and next_token.val[1] == "?":
                            v = next_token.val[1]
                        token = TOK.Punctuation(token.concatenate(next_token), v)
                        next_token = next(token_stream)
                    # We may be finishing a sentence with not only a period but also
                    # right parenthesis and quotation marks
                    while (
                        next_token.kind == TOK.PUNCTUATION
                        and next_token.val[1] in SENTENCE_FINISHERS
                    ):
                        yield token
                        token = next_token
                        next_token = next(token_stream)
                    # The sentence is definitely finished now
                    yield token
                    token = tok_end_sentence
                    in_sentence = False

            yield token
            token = next_token

    except StopIteration:
        pass

    # Final token (previous lookahead)
    if token is not None and token.kind != TOK.S_SPLIT:
        if not in_sentence and token.kind not in TOK.END:
            # Starting something here
            yield tok_begin_sentence
            in_sentence = True
        yield token
        if in_sentence and token.kind in {TOK.S_END, TOK.P_END}:
            in_sentence = False

    # Done with the input stream
    # If still inside a sentence, finish it
    if in_sentence:
        yield tok_end_sentence


def match_stem_list(token, stems):
    """ Find the stem of a word token in given dict, or return None if not found """
    if token.kind != TOK.WORD:
        return None
    return stems.get(token.txt.lower(), None)


def month_for_token(token, after_ordinal=False):
    """ Return a number, 1..12, corresponding to a month name,
        or None if the token does not contain a month name """
    if not after_ordinal and token.txt in MONTH_BLACKLIST:
        # Special case for 'Ágúst', which we do not recognize
        # as a month name unless it follows an ordinal number
        return None
    return match_stem_list(token, MONTHS)


def parse_phrases_1(token_stream):
    """ Handle dates and times """

    token = None
    try:

        # Maintain a one-token lookahead
        token = next(token_stream)
        while True:

            next_token = next(token_stream)
            # Coalesce abbreviations and trailing period
            if token.kind == TOK.WORD and next_token.txt == ".":
                abbrev = token.txt + next_token.txt
                if abbrev in Abbreviations.FINISHERS:
                    token = TOK.Word(token.concatenate(next_token), token.val)
                    next_token = next(token_stream)

            # Coalesce [year|number] + ['e.Kr.'|'f.Kr.'] into year
            if token.kind == TOK.YEAR or token.kind == TOK.NUMBER:
                val = token.val if token.kind == TOK.YEAR else token.val[0]
                nval = None
                if next_token.txt in BCE:  # f.Kr.
                    # Yes, we set year X BCE as year -X ;-)
                    nval = -val
                elif next_token.txt in CE:  # e.Kr.
                    nval = val
                if nval is not None:
                    token = TOK.Year(token.concatenate(next_token, separator=" "), nval)
                    next_token = next(token_stream)
                    if next_token.txt == ".":
                        token = TOK.Year(token.concatenate(next_token), nval)
                        next_token = next(token_stream)
            # TODO: "5 mars" greinist sem dagsetning, vantar punktinn.
            # Check for [number | ordinal] [month name]
            if (
                token.kind == TOK.ORDINAL or token.kind == TOK.NUMBER
            ) and next_token.kind == TOK.WORD:

                if next_token.txt == "gr.":
                    # Corner case: If we have an ordinal followed by
                    # the abbreviation "gr.", we assume that the only
                    # interpretation of the abbreviation is "grein".
                    next_token = TOK.Word(
                        next_token, [("grein", 0, "kvk", "skst", "gr.", "-")]
                    )

                month = month_for_token(next_token, True)
                if month is not None:
                    token = TOK.Date(
                        token.concatenate(next_token, separator=" "),
                        y=0,
                        m=month,
                        d=token.val if token.kind == TOK.ORDINAL else token.val[0],
                    )
                    # Eat the month name token
                    next_token = next(token_stream)

            # Check for [date] [year]
            if token.kind == TOK.DATE and next_token.kind == TOK.YEAR:

                if not token.val[0]:
                    # No year yet: add it
                    token = TOK.Date(
                        token.concatenate(next_token, separator=" "),
                        y=next_token.val,
                        m=token.val[1],
                        d=token.val[2],
                    )
                    # Eat the year token
                    next_token = next(token_stream)

            # Check for [date] [time]
            if token.kind == TOK.DATE and next_token.kind == TOK.TIME:
                # Create a time stamp
                y, mo, d = token.val
                h, m, s = next_token.val
                token = TOK.Timestamp(
                    token.concatenate(next_token, separator=" "), y=y, mo=mo, d=d, h=h, m=m, s=s
                )
                # Eat the time token
                next_token = next(token_stream)

            if (
                token.kind == TOK.NUMBER
                and next_token.kind == TOK.TELNO
                and token.txt in COUNTRY_CODES
            ):
                # Check for country code in front of telephone number
                token = TOK.Telno(
                    token.concatenate(next_token, separator=" "), next_token.val[0], cc=token.txt
                )
                next_token = next(token_stream)

            # Yield the current token and advance to the lookahead
            yield token
            token = next_token

    except StopIteration:
        pass

    # Final token (previous lookahead)
    if token:
        yield token


def parse_date_and_time(token_stream):
    """ Handle dates and times, absolute and relative. """

    token = None
    try:

        # Maintain a one-token lookahead
        token = next(token_stream)

        while True:

            next_token = next(token_stream)

            # TODO: "5 mars" endar sem dagsetning. Þarf að geta merkt.
            # DATEABS and DATEREL made
            # Check for [number | ordinal] [month name]
            if (
                token.kind == TOK.ORDINAL
                or token.kind == TOK.NUMBER
                # or (token.txt and token.txt.lower() in DAYS_OF_MONTH)
            ) and next_token.kind == TOK.WORD:
                month = month_for_token(next_token, True)
                if month is not None:
                    token = TOK.Date(
                        token.concatenate(next_token, separator=" "),
                        y=0,
                        m=month,
                        d=(
                            token.val
                            if token.kind == TOK.ORDINAL
                            else token.val[0]
                            # if token.kind == TOK.NUMBER
                            # else DAYS_OF_MONTH[token.txt.lower()]
                        ),
                    )
                    # Eat the month name token
                    next_token = next(token_stream)

            # Check for [DATE] [year]
            if token.kind == TOK.DATE and (
                next_token.kind == TOK.NUMBER or next_token.kind == TOK.YEAR
            ):
                if not token.val[0]:
                    # No year yet: add it
                    year = (
                        next_token.val
                        if next_token.kind == TOK.YEAR
                        else next_token.val[0]
                        if 1776 <= next_token.val[0] <= 2100
                        else 0
                    )
                    if year != 0:
                        token = TOK.Date(
                            token.concatenate(next_token, separator=" "),
                            y=year,
                            m=token.val[1],
                            d=token.val[2],
                        )
                        # Eat the year token
                        next_token = next(token_stream)

            # Check for [month name] [year|YEAR]
            if token.kind == TOK.WORD and (
                next_token.kind == TOK.NUMBER or next_token.kind == TOK.YEAR
            ):
                month = month_for_token(token)
                if month is not None:
                    year = (
                        next_token.val
                        if next_token.kind == TOK.YEAR
                        else next_token.val[0]
                        if 1776 <= next_token.val[0] <= 2100
                        else 0
                    )
                    if year != 0:
                        token = TOK.Date(
                            token.concatenate(next_token, separator=" "), y=year, m=month, d=0
                        )
                        # Eat the year token
                        next_token = next(token_stream)

            # Check for a single month, change to DATEREL
            if token.kind == TOK.WORD:
                month = month_for_token(token)
                # Don't automatically interpret "mar", etc. as month names,
                # since they are ambiguous
                if month is not None and token.txt not in AMBIGUOUS_MONTH_NAMES:
                    token = TOK.Daterel(token, y=0, m=month, d=0)

            # Split DATE into DATEABS and DATEREL
            if token.kind == TOK.DATE:
                if token.val[0] and token.val[1] and token.val[2]:
                    token = TOK.Dateabs(
                        token, y=token.val[0], m=token.val[1], d=token.val[2]
                    )
                else:
                    token = TOK.Daterel(
                        token, y=token.val[0], m=token.val[1], d=token.val[2]
                    )

            # Split TIMESTAMP into TIMESTAMPABS and TIMESTAMPREL
            if token.kind == TOK.TIMESTAMP:
                if all(x != 0 for x in token.val[0:3]):
                    # Year, month and day all non-zero (h, m, s can be zero)
                    token = TOK.Timestampabs(token, *token.val)
                else:
                    token = TOK.Timestamprel(token, *token.val)

            # Swallow "e.Kr." and "f.Kr." postfixes
            if token.kind == TOK.DATEABS:
                if next_token.kind == TOK.WORD and next_token.txt in CE_BCE:
                    y = token.val[0]
                    if next_token.txt in BCE:
                        # Change year to negative number
                        y = -y
                    token = TOK.Dateabs(
                        token.concatenate(next_token, separator=" "),
                        y=y,
                        m=token.val[1],
                        d=token.val[2],
                    )
                    # Swallow the postfix
                    next_token = next(token_stream)

            # Check for [date] [time] (absolute)
            if token.kind == TOK.DATEABS:
                if next_token.kind == TOK.TIME:
                    # Create an absolute time stamp
                    y, mo, d = token.val
                    h, m, s = next_token.val
                    token = TOK.Timestampabs(
                        token.concatenate(next_token, separator=" "), y=y, mo=mo, d=d, h=h, m=m, s=s
                    )
                    # Eat the time token
                    next_token = next(token_stream)

            # Check for [date] [time] (relative)
            if token.kind == TOK.DATEREL:
                if next_token.kind == TOK.TIME:
                    # Create a time stamp
                    y, mo, d = token.val
                    h, m, s = next_token.val
                    token = TOK.Timestamprel(
                        token.concatenate(next_token, separator=" "), y=y, mo=mo, d=d, h=h, m=m, s=s
                    )
                    # Eat the time token
                    next_token = next(token_stream)

            # Yield the current token and advance to the lookahead
            yield token
            token = next_token

    except StopIteration:
        pass

    # Final token (previous lookahead)
    if token:
        yield token


def parse_phrases_2(token_stream, coalesce_percent=False):
    """ Handle numbers, amounts and composite words. """

    token = None
    try:

        # Maintain a one-token lookahead
        token = next(token_stream)

        while True:

            next_token = next(token_stream)

            # Logic for numbers and fractions that are partially or entirely
            # written out in words

            def number(tok):
                """ If the token denotes a number, return that number - or None """
                if tok.txt.lower() == "áttu":
                    # Do not accept 'áttu' (stem='átta', no kvk) as a number
                    return None
                return match_stem_list(tok, MULTIPLIERS)

            # Check whether we have an initial number word
            multiplier = number(token) if token.kind == TOK.WORD else None

            # Check for [number] 'hundred|thousand|million|billion'
            while (
                token.kind == TOK.NUMBER or multiplier is not None
            ) and next_token.kind == TOK.WORD:

                multiplier_next = number(next_token)

                def convert_to_num(token):
                    if multiplier is not None:
                        token = TOK.Number(token, multiplier)
                    return token

                if multiplier_next is not None:
                    # Retain the case of the last multiplier
                    token = convert_to_num(token)
                    token = TOK.Number(
                        token.concatenate(next_token, separator=" "), token.val[0] * multiplier_next
                    )
                    # Eat the multiplier token
                    next_token = next(token_stream)
                elif next_token.txt in AMOUNT_ABBREV:
                    # Abbreviations for ISK amounts
                    # For abbreviations, we do not know the case,
                    # but we try to retain the previous case information if any
                    token = convert_to_num(token)
                    token = TOK.Amount(
                        token.concatenate(next_token, separator=" "),
                        "ISK",
                        token.val[0] * AMOUNT_ABBREV[next_token.txt],
                    )
                    next_token = next(token_stream)
                elif next_token.txt in CURRENCY_ABBREV:
                    # A number followed by an ISO currency abbreviation
                    token = convert_to_num(token)
                    token = TOK.Amount(
                        token.concatenate(next_token, separator=" "), next_token.txt, token.val[0]
                    )
                    next_token = next(token_stream)
                else:
                    # Check for [number] 'prósent/prósentustig/hundraðshluta'
                    if coalesce_percent:
                        percentage = match_stem_list(next_token, PERCENTAGES)
                    else:
                        percentage = None
                    if percentage is None:
                        break
                    # We have '17 prósent': coalesce into a single token
                    token = convert_to_num(token)
                    token = TOK.Percent(token.concatenate(next_token, separator=" "), token.val[0])
                    # Eat the percent word token
                    next_token = next(token_stream)

                multiplier = None

            # Check for [currency] [number] (e.g. kr. 9.900 or USD 50)
            if next_token.kind == TOK.NUMBER and (
                token.txt in ISK_AMOUNT_PRECEDING or token.txt in CURRENCY_ABBREV
            ):
                curr = "ISK" if token.txt in ISK_AMOUNT_PRECEDING else token.txt
                token = TOK.Amount(
                    token.concatenate(next_token, separator=" "), curr, next_token.val[0]
                )
                next_token = next(token_stream)

            # Check for composites:
            # 'stjórnskipunar- og eftirlitsnefnd'
            # 'dómsmála-, viðskipta- og iðnaðarráðherra'
            tq = []
            while (
                token.kind == TOK.WORD
                and next_token.kind == TOK.PUNCTUATION
                and next_token.val[1] == COMPOSITE_HYPHEN
            ):
                # Accumulate the prefix in tq
                tq.append(token)
                tq.append(TOK.Punctuation(next_token, normalized=HYPHEN))
                # Check for optional comma after the prefix
                comma_token = next(token_stream)
                if comma_token.kind == TOK.PUNCTUATION and comma_token.val[1] == ",":
                    # A comma is present: append it to the queue
                    # and skip to the next token
                    tq.append(comma_token)
                    comma_token = next(token_stream)
                # Reset our two lookahead tokens
                token = comma_token
                next_token = next(token_stream)

            if tq:
                # We have accumulated one or more prefixes
                # ('dómsmála-, viðskipta-')
                if token.kind == TOK.WORD and token.txt in ("og", "eða"):
                    # We have 'viðskipta- og'
                    if next_token.kind != TOK.WORD:
                        # Incorrect: yield the accumulated token
                        # queue and keep the current token and the
                        # next_token lookahead unchanged
                        for t in tq:
                            yield t
                    else:
                        # We have 'viðskipta- og iðnaðarráðherra'
                        # Return a single token with the meanings of
                        # the last word, but an amalgamated token text.
                        # Note: there is no meaning check for the first
                        # part of the composition, so it can be an unknown word.
                        # XXX: We lose origin tracking here!
                        txt = " ".join(t.txt for t in tq + [token, next_token])
                        txt = txt.replace(" -", "-").replace(" ,", ",")
                        token = Tok(TOK.WORD, txt, None)
                        next_token = next(token_stream)
                else:
                    # Incorrect prediction: make amends and continue
                    for t in tq:
                        yield t

            # Yield the current token and advance to the lookahead
            yield token
            token = next_token

    except StopIteration:
        pass

    # Final token (previous lookahead)
    if token:
        yield token


def tokenize(text_or_gen, **options):
    """ Tokenize text in several phases, returning a generator
        (iterable sequence) of tokens that processes tokens on-demand. """

    # Thank you Python for enabling this programming pattern ;-)

    # Make sure that the abbreviation config file has been read
    Abbreviations.initialize()
    with_annotation = options.pop("with_annotation", True)
    coalesce_percent = options.pop("coalesce_percent", False)

    token_stream = parse_tokens(text_or_gen, **options)
    token_stream = parse_particles(token_stream, **options)
    token_stream = parse_sentences(token_stream)
    token_stream = parse_phrases_1(token_stream)
    token_stream = parse_date_and_time(token_stream)

    # Skip the parse_phrases_2 pass if the with_annotation option is False
    if with_annotation:
        token_stream = parse_phrases_2(token_stream, coalesce_percent=coalesce_percent)

    return (t for t in token_stream if t.kind != TOK.X_END)


def tokenize_without_annotation(text_or_gen, **options):
    """ Tokenize without the last pass which can be done more thoroughly if BÍN
        annotation is available, for instance in GreynirPackage. """
    return tokenize(text_or_gen, with_annotation=False, **options)


def split_into_sentences(text_or_gen, **options):
    """ Shallow tokenization of the input text, which can be either
        a text string or a generator of lines of text (such as a file).
        This function returns a generator of strings, where each string
        is a sentence, and tokens are separated by spaces. """
    if options.pop("normalize", False):
        to_text = normalized_text
    else:
        to_text = lambda t: t.txt
    curr_sent = []
    for t in tokenize_without_annotation(text_or_gen, **options):
        if t.kind in TOK.END:
            # End of sentence/paragraph
            if curr_sent:
                yield " ".join(curr_sent)
                curr_sent = []
        else:
            txt = to_text(t)
            if txt:
                curr_sent.append(txt)
    if curr_sent:
        yield " ".join(curr_sent)


def mark_paragraphs(txt):
    """ Insert paragraph markers into plaintext, by newlines """
    if not txt:
        return "[[ ]]"
    return "[[ " + " ]] [[ ".join(txt.split("\n")) + " ]]"


def paragraphs(tokens):
    """ Generator yielding paragraphs from token iterable. Each paragraph is a list
        of sentence tuples. Sentence tuples consist of the index of the first token
        of the sentence (the TOK.S_BEGIN token) and a list of the tokens within the
        sentence, not including the starting TOK.S_BEGIN or the terminating TOK.S_END
        tokens. """

    if not tokens:
        return

    def valid_sent(sent):
        """ Return True if the token list in sent is a proper
            sentence that we want to process further """
        if not sent:
            return False
        # A sentence with only punctuation is not valid
        return any(t[0] != TOK.PUNCTUATION for t in sent)

    sent = []  # Current sentence
    sent_begin = 0
    current_p = []  # Current paragraph

    for ix, t in enumerate(tokens):
        t0 = t[0]
        if t0 == TOK.S_BEGIN:
            sent = []
            sent_begin = ix
        elif t0 == TOK.S_END:
            if valid_sent(sent):
                # Do not include or count zero-length sentences
                current_p.append((sent_begin, sent))
            sent = []
        elif t0 == TOK.P_BEGIN or t0 == TOK.P_END:
            # New paragraph marker: Start a new paragraph if we didn't have one before
            # or if we already had one with some content
            if valid_sent(sent):
                current_p.append((sent_begin, sent))
            sent = []
            if current_p:
                yield current_p
                current_p = []
        else:
            sent.append(t)

    if valid_sent(sent):
        current_p.append((sent_begin, sent))
    if current_p:
        yield current_p


RE_SPLIT_STR = (
    # The following regex catches Icelandic numbers with dots and a comma
    r"([\+\-\$€]?\d{1,3}(?:\.\d\d\d)+\,\d+)"  # +123.456,789
    # The following regex catches English numbers with commas and a dot
    r"|([\+\-\$€]?\d{1,3}(?:\,\d\d\d)+\.\d+)"  # +123,456.789
    # The following regex catches Icelandic numbers with a comma only
    r"|([\+\-\$€]?\d+\,\d+(?!\.\d))"  # -1234,56
    # The following regex catches English numbers with a dot only
    r"|([\+\-\$€]?\d+\.\d+(?!\,\d))"  # -1234.56
    # Finally, space and punctuation
    r"|([~\s"
    + "".join("\\" + c for c in PUNCTUATION)
    + r"])"
)
RE_SPLIT = re.compile(RE_SPLIT_STR)


def correct_spaces(s):
    """ Utility function to split and re-compose a string
        with correct spacing between tokens.
        NOTE that this function uses a quick-and-dirty approach
        which may not handle all edge cases! """
    r = []
    last = TP_NONE
    double_quote_count = 0
    for w in RE_SPLIT.split(s):
        if w is None:
            continue
        w = w.strip()
        if not w:
            continue
        if len(w) > 1:
            this = TP_WORD
        elif w == '"':
            # For English-type double quotes, we glue them alternatively
            # to the right and to the left token
            this = (TP_LEFT, TP_RIGHT)[double_quote_count % 2]
            double_quote_count += 1
        elif w in LEFT_PUNCTUATION:
            this = TP_LEFT
        elif w in RIGHT_PUNCTUATION:
            this = TP_RIGHT
        elif w in NONE_PUNCTUATION:
            this = TP_NONE
        elif w in CENTER_PUNCTUATION:
            this = TP_CENTER
        else:
            this = TP_WORD
        if (
            (w == "og" or w == "eða")
            and len(r) >= 2
            and r[-1] == "-"
            and r[-2].lstrip().isalpha()
        ):
            # Special case for compounds such as "fjármála- og efnahagsráðuneytið"
            # and "Iðnaðar-, ferðamála- og atvinnuráðuneytið":
            # detach the hyphen from "og"/"eða"
            r.append(" " + w)
        elif (
            this == TP_WORD
            and len(r) >= 2
            and r[-1] == "-"
            and w.isalpha()
            and (r[-2] == "," or r[-2].lstrip() in ("og", "eða"))
        ):
            # Special case for compounds such as
            # "bensínstöðvar, -dælur og -tankar"
            r[-1] = " -"
            r.append(w)
        elif TP_SPACE[last - 1][this - 1] and r:
            r.append(" " + w)
        else:
            r.append(w)
        last = this
    return "".join(r)


def detokenize(tokens, normalize=False):
    """ Utility function to convert an iterable of tokens back
        to a correctly spaced string. If normalize is True,
        punctuation is normalized before assembling the string. """
    to_text = normalized_text if normalize else lambda t: t.txt
    r = []
    last = TP_NONE
    double_quote_count = 0
    for t in tokens:
        w = to_text(t)
        if not w:
            continue
        this = TP_WORD
        if t.kind == TOK.PUNCTUATION:
            if len(w) > 1:
                pass
            elif w == '"':
                # For English-type double quotes, we glue them alternatively
                # to the right and to the left token
                this = (TP_LEFT, TP_RIGHT)[double_quote_count % 2]
                double_quote_count += 1
            elif w in LEFT_PUNCTUATION:
                this = TP_LEFT
            elif w in RIGHT_PUNCTUATION:
                this = TP_RIGHT
            elif w in NONE_PUNCTUATION:
                this = TP_NONE
            elif w in CENTER_PUNCTUATION:
                this = TP_CENTER
        if TP_SPACE[last - 1][this - 1] and r:
            r.append(" " + w)
        else:
            r.append(w)
        last = this
    return "".join(r)
