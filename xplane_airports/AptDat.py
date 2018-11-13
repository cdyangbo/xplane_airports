"""
Tools for reading, inspecting, and manipulating X-Plane’s airport (apt.dat) files.
"""

from contextlib import suppress
from dataclasses import dataclass, field
from operator import attrgetter
import re
from enum import Enum
from typing import List

WED_LINE_ENDING = '\n'


class RunwayType(Enum):
    """Row codes used to identify different types of runways"""
    LAND_RUNWAY = 100
    WATER_RUNWAY = 101
    HELIPAD = 102

    def __int__(self):
        return self.value

class AptDatLine:
    """
    A single line from an apt.dat file.
    """
    def __init__(self, line_text):
        """
        :type line_text: str
        """
        self.raw = line_text
        self.row_code = self.raw.strip().split(' ')[0]
        with suppress(ValueError):
            self.row_code = int(self.row_code)

    def is_runway(self):
        """
        :returns: True if this line represents a land runway, waterway, or helipad
        :rtype: bool
        """
        return self.row_code in [int(RunwayType.LAND_RUNWAY), int(RunwayType.WATER_RUNWAY), int(RunwayType.HELIPAD)]

    def is_ignorable(self):
        """
        :returns: True if this line carries no semantic value for any airport in the apt.dat file.
        :rtype: bool
        """
        return self.row_code == 99 or self.is_file_header() or not self.raw.strip()

    def is_airport_header(self):
        """
        :returns: True if this line marks the beginning of an airport, seaport, or heliport
        :rtype: bool
        """
        return self.row_code in [1, 16, 17]

    def is_file_header(self):
        """
        :returns: True if this is part of an apt.dat file header
        :rtype: bool
        """
        return self.row_code in ['I', 'A'] or "Generated by WorldEditor" in self.raw

    @property
    def runway_type(self):
        """
        :returns: The type of runway represented by this line
        :rtype: RunwayType
        """
        assert self.is_runway()
        return RunwayType(self.row_code)

    @property
    def tokens(self):
        """
        :returns: The tokens in this line
        :rtype: list[str]
        """
        return str(self).split(' ')

    def __str__(self):
        return re.sub(' +', ' ', self.raw.strip())  # Strip, and replace multiple spaces with a single

    def __bool__(self):
        return not self.is_ignorable()


@dataclass
class Airport:
    """A single airport from an apt.dat file."""
    name: str                     # The name of the airport, like "Seattle-Tacoma Intl"
    id: str                       # The X-Plane identifier for the airport, which may or may not correspond to its ICAO ID
    from_file: str = ''           # Path to the apt.dat file from which this airport was read
    has_atc: bool = False         # True if the airport header indicates the airport has air traffic control
    elevation_ft_amsl: float = 0  # The elevation, in feat above mean sea level, indicated in the airport header line
    text: List[AptDatLine] = field(default_factory=list)  # The complete text of the portion of the apt.dat file pertaining to this airport

    def __bool__(self):
        return bool(self.id)

    def __str__(self):
        return WED_LINE_ENDING.join(line.raw for line in self.text)

    def head(self, num_lines=10):
        """
        :param num_lines: The max number of lines to return
        :return: The first `num_lines` of the apt.dat text for this airport
        :rtype: str
        """
        return WED_LINE_ENDING.join(line.raw for i, line in enumerate(self.text) if i < num_lines)

    def write_to_disk(self, path_to_write_to):
        """
        Writes a complete apt.dat file containing only this airport
        :param path_to_write_to: A complete file path (ending in .dat)
        :type path_to_write_to: str
        """
        assert path_to_write_to.endswith('.dat')
        with open(path_to_write_to, 'w') as f:
            f.write("I" + WED_LINE_ENDING)
            f.write("1100 Generated by WorldEditor" + WED_LINE_ENDING + WED_LINE_ENDING)
            f.write(str(self))
            f.write("99" + WED_LINE_ENDING)

    @property
    def has_taxiway(self):
        """
        :returns: True if this airport defines any taxiway geometry
        :rtype: bool
        """
        return self.has_row_code([113, 114])

    @property
    def has_taxi_route(self):
        """
        :returns: True if this airport defines routing rules for ATC's use of its taxiways.
        :rtype: bool
        """
        return self.has_row_code(1200)

    @property
    def has_traffic_flow(self):
        """
        :returns: True if this airport defines rules for when and under what conditions certain runways should be used by ATC
        :rtype: bool
        """
        return self.has_row_code(1000)

    @property
    def has_ground_routes(self):
        """
        :returns: True if this airport defines any destinations for ground vehicles (like baggage cars, fuel trucks, etc.), ground truck parking locations, or taxi routes
        :rtype: bool
        """
        return self.has_row_code([1400, 1401, 1200])

    @property
    def has_taxiway_sign(self):
        """
        :returns: True if this airport defines any taxi signs
        :rtype: bool
        """
        return self.has_row_code(20)

    @property
    def has_comm_freq(self):
        """
        :returns: True if this airport defines communication radio frequencies for interacting with ATC
        :rtype: bool
        """
        return self.has_row_code([50, 51, 52, 53, 54, 55, 56])

    def has_row_code(self, row_code_or_codes):
        """
        :param row_code_or_codes: One or more "row codes" (the first token at the beginning of a line; almost always int)
        :type row_code_or_codes: Union[int, str, collections.Iterable[int]]
        :returns: True if the airport has any lines in its text that begin with the specified row code(s)
        :rtype: bool
        """
        if isinstance(row_code_or_codes, int) or isinstance(row_code_or_codes, str):
            return any(line for line in self.text if line.row_code == row_code_or_codes)
        return any(line for line in self.text if line.row_code in row_code_or_codes)

    @property
    def latitude(self):
        """
        :returns: The latitude of the airport, which X-Plane calculates as the latitude of the center of the first runway.
        :rtype: float
        """
        runways = list(line for line in self.text if line.is_runway())
        assert runways, "Airport appears to have no runway lines"
        rwy_0 = runways[0]
        if rwy_0.runway_type == RunwayType.LAND_RUNWAY:
            return 0.5 * (float(rwy_0.tokens[9]) + float(rwy_0.tokens[18]))
        elif rwy_0.runway_type == RunwayType.WATER_RUNWAY:
            return 0.5 * (float(rwy_0.tokens[4]) + float(rwy_0.tokens[7]))
        elif rwy_0.runway_type == RunwayType.HELIPAD:
            return float(rwy_0.tokens[2])

    @property
    def longitude(self):
        """
        :returns: The longitude of the airport, which X-Plane calculates as the longitude of the center of the first runway.
        :rtype: float
        """
        runways = list(line for line in self.text if line.is_runway())
        assert runways, "Airport appears to have no runway lines"
        rwy_0 = runways[0]
        if rwy_0.runway_type == RunwayType.LAND_RUNWAY:
            return 0.5 * (float(rwy_0.tokens[10]) + float(rwy_0.tokens[19]))
        elif rwy_0.runway_type == RunwayType.WATER_RUNWAY:
            return 0.5 * (float(rwy_0.tokens[5]) + float(rwy_0.tokens[8]))
        elif rwy_0.runway_type == RunwayType.HELIPAD:
            return float(rwy_0.tokens[3])

    @staticmethod
    def from_lines(apt_dat_lines, from_file_name):
        """
        :param apt_dat_lines: The lines of the apt.dat file (either strings or parsed AptDatLine objects)
        :type apt_dat_lines: collections.Iterable[AptDatLine|str]
        :param from_file_name: The name of the apt.dat file you read this airport in from
        :type from_file_name: str
        :rtype: Airport
        """
        lines = list(line if isinstance(line, AptDatLine) else AptDatLine(line) for line in apt_dat_lines)
        apt_header_lines = list(line for line in lines if line.is_airport_header())
        assert len(apt_header_lines), "Failed to find an airport header line in airport from file %s" % from_file_name
        assert len(apt_header_lines) == 1, "Expected only one airport header line in airport from file %s" % from_file_name
        return Airport(name=' '.join(apt_header_lines[0].tokens[5:]),
                       id=apt_header_lines[0].tokens[4],
                       from_file=from_file_name,
                       elevation_ft_amsl=float(apt_header_lines[0].tokens[1]),
                       has_atc=bool(int(apt_header_lines[0].tokens[2])),  # '0' or '1'
                       text=lines)

    @staticmethod
    def from_str(file_text, from_file_name):
        """
        :param file_text: The portion of the apt.dat file text that specifies this airport
        :type file_text: str
        :param from_file_name: The name of the apt.dat file you read this airport in from
        :type from_file_name: str
        :rtype: Airport
        """
        return Airport.from_lines((AptDatLine(line) for line in file_text.splitlines()), from_file_name)


class AptDat:
    """
    A container class for ``Airport`` objects.
    Parses X-Plane's gigantic apt.dat files, which may have data on hundreds of airports.
    """
    def __init__(self, path_to_file=None):
        """
        :param path_to_file Location of the apt.dat (or ICAO.dat) file to read from disk
        :type path_to_file: str
        """
        self.airports = []
        """:type: list[Airport]"""

        self.path_to_file = path_to_file
        if self.path_to_file:
            with open(self.path_to_file, 'r') as f:
                self._parse_text(f.readlines(), path_to_file)

    @staticmethod
    def from_file_text(apt_dat_file_text, from_file):
        """
        :param apt_dat_file_text: The contents of an apt.dat (or ICAO.dat) file
        :type apt_dat_file_text: str
        :param from_file: Path to the file from which this was read
        :type from_file: str
        """
        return AptDat()._parse_text(apt_dat_file_text, from_file)

    def _parse_text(self, apt_dat_text, from_file):
        if not isinstance(apt_dat_text, list):  # Must be a newline-containing string
            assert isinstance(apt_dat_text, str)
            apt_dat_text = apt_dat_text.splitlines()

        self.path_to_file = from_file
        apt_lines = []
        for line in (AptDatLine(l) for l in apt_dat_text):
            if line.is_airport_header():
                if apt_lines:  # finish off the previous airport
                    self.airports.append(Airport.from_lines(apt_lines, from_file))
                apt_lines = [line]
            elif not line.is_ignorable():
                apt_lines.append(line)
        if apt_lines:  # finish off the final airport
            self.airports.append(Airport.from_lines(apt_lines, from_file))
        return self

    def write_to_disk(self, path_to_write_to):
        """
        Writes a complete apt.dat file containing this entire collection of airports.
        :param path_to_write_to: A complete file path (ending in .dat)
        :type path_to_write_to: str
        """
        assert path_to_write_to.endswith('.dat')
        with open(path_to_write_to, 'w') as f:
            f.write("I" + WED_LINE_ENDING)
            f.write("1100 Generated by WorldEditor" + WED_LINE_ENDING + WED_LINE_ENDING)
            for apt in self.airports:
                f.write(str(apt))
                f.write(WED_LINE_ENDING * 2)
            f.write("99" + WED_LINE_ENDING)

    def sort(self, key='name'):
        """
        By default, we store the airport data in whatever order we read it from the apt.dat file.
        When you call sort, though, we'll ensure that it's in order (default to name order, just like it's always
        been in the shipping versions of X-Plane).

        :param key: The ``Airport`` key to sort on
        :type key: str
        """
        self.airports = sorted(self.airports, key=attrgetter(key))

    def search_by_id(self, apt_id):
        """
        :param apt_id: The X-Plane ID of the airport you want to query
        :type apt_id: str
        :returns: The airport with the specified ID, or ``None`` if no matching airport exists in this collection.
        :rtype: Union[Airport, None]
        """
        found = self.search_by_predicate(lambda apt: apt.id.upper() == apt_id.upper())
        if found:
            assert len(found) == 1, "No two airports in a given apt.dat file should ever have the same airport code"
            return found[0]
        return None

    def search_by_name(self, apt_name):
        """
        :param apt_name: The name of the airport you want to query
        :type apt_name: str
        :rtype: list[Airport]
        :returns: All airports that match the specified name, case-insensitive (an empty list if no airports match)
        """
        return self.search_by_predicate(lambda apt: apt.name.upper() == apt_name.upper())

    def search_by_predicate(self, predicate_fn):
        """
        :param predicate_fn: We will collect all airports for which this function returns ``True``
        :type predicate_fn: (Airport) -> bool
        :rtype: list[Airport]
        """
        return list(apt for apt in self.airports if predicate_fn(apt))

    @property
    def ids(self):
        """
        :returns: A generator containing the X-Plane IDs of all airports in the collection. Note that these IDs may or may not correspond to the airports' ICAO identifiers.
        :rtype: collection.Iterable[str]
        """
        return (apt.id for apt in self.airports)

    @property
    def names(self):
        """
        :returns: A generator containing the names of all airports in the collection
        :rtype: collection.Iterable[str]
        """
        return (apt.name for apt in self.airports)

    def __str__(self):
        """
        :returns: The raw text of the complete apt.dat file
        :rtype: str
        """
        return WED_LINE_ENDING.join(str(apt) for apt in self.airports)

    def __getitem__(self, key):
        """
        Returns the airport at the specified index (if ``key`` is an int), or with the specified identifier or name (if ``key`` is a string), or ``None`` if no airport could be found using the above criteria.
        :param key: int|str
        :rtype: Airport
        """
        if isinstance(key, int):
            assert key < len(self.airports), "Tried to access index %d, but this AptDat only has %d airports" % (key, len(self.airports))
            return self.airports[key]
        assert isinstance(key, str)
        for pred in [self.search_by_id, self.search_by_name]:
            result = pred(key)
            if result:
                return result
        raise KeyError("No airport with ID or name '%s'" % key)

    def __repr__(self):
        return str(list(self.ids))

    def __eq__(self, other):
        return self.airports == other.airports

    def __iter__(self):
        return (apt for apt in self.airports)

    def __len__(self):
        return len(self.airports)

    def __concat__(self, other):
        """
        Get a new airport data object that combines the airport data in other with the data in this object.
        Note that no de-duplication will occur---it's your job to make sure the two airport data are disjoint.
        :type other: AptDat
        :rtype: AptDat
        """
        out = AptDat()
        out.airports = list(self.airports) + list(other.airports)
        return out

    def __iconcat__(self, other):
        """
        Add the airport data in other to the data in this object.
        Note that no de-duplication will occur---it's your job to make sure the two airport data are disjoint.
        :type other: AptDat
        """
        self.airports += list(other.airports)

    def __add__(self, apt):
        """
        Add the airport data in other to the data in this object.
        Note that no de-duplication will occur---it's your job to make sure the two airport data are disjoint.
        :type apt: Airport
        """
        out = AptDat()
        out.airports = self.airports + [apt]
        return out

    def __iadd__(self, apt):
        """
        Add the airport data in other to the data in this object.
        Note that no de-duplication will occur---it's your job to make sure the two airport data are disjoint.
        :type apt: Airport
        """
        self.airports.append(apt)
        return self
