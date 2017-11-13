from collections import deque, namedtuple
from itertools import chain
from typing import List

import matplotlib.pyplot as plt
from django.core import checks
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from shapely import speedups
from shapely.geometry import LinearRing, LineString, Point, Polygon
from shapely.ops import unary_union

if speedups.available:
    speedups.enable()


@checks.register()
def check_speedups(app_configs, **kwargs):
    errors = []
    if not speedups.available:
        errors.append(
            checks.Warning(
                'Your shapely version does not have speedups enabled. This will significantly slow down c3nav!',
                obj='rtree.index.Index',
                id='c3nav.mapdata.W001',
            )
        )
    return errors


def clean_geometry(geometry):
    """
    if the given geometry is a Polygon and invalid, try to make it valid if it results in a Polygon (not MultiPolygon)
    """
    if geometry.is_valid:
        return geometry

    if isinstance(geometry, Polygon):
        return geometry.buffer(0)

    return geometry


def assert_multipolygon(geometry):
    """
    given a Polygon or a MultiPolygon, return a list of Polygons
    :param geometry: a Polygon or a MultiPolygon
    :return: a list of Polygons
    """
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    return [geom for geom in geometry.geoms if isinstance(geom, Polygon)]


def assert_multilinestring(geometry):
    """
    given a LineString or MultiLineString, return a list of LineStrings
    :param geometry: a LineString or a MultiLineString
    :return: a list of LineStrings
    """
    if geometry.is_empty:
        return []
    if isinstance(geometry, LineString):
        return [geometry]
    return [geom for geom in geometry.geoms if isinstance(geom, LineString)]


def plot_geometry(geom, title=None, bounds=None):
    fig = plt.figure()
    axes = fig.add_subplot(111)
    if bounds is None:
        bounds = geom.bounds
    axes.set_xlim(bounds[0], bounds[2])
    axes.set_ylim(bounds[1], bounds[3])
    verts = []
    codes = []
    if not isinstance(geom, (tuple, list)):
        geom = assert_multipolygon(geom)
    else:
        geom = tuple(chain(*(assert_multipolygon(g) for g in geom)))
    for polygon in geom:
        for ring in chain([polygon.exterior], polygon.interiors):
            verts.extend(ring.coords)
            codes.append(Path.MOVETO)
            codes.extend((Path.LINETO,) * len(ring.coords))
            verts.append(verts[-1])

    if title is not None:
        plt.title(title)

    path = Path(verts, codes)
    patch = PathPatch(path)
    axes.add_patch(patch)
    plt.show()


def get_rings(geometry):
    if isinstance(geometry, Polygon):
        return chain((geometry.exterior, ), geometry.interiors)
    try:
        geoms = geometry.geoms
    except AttributeError:
        pass
    else:
        return chain(*(get_rings(geom) for geom in geoms))

    if isinstance(geometry, LinearRing):
        return (geometry, )

    return ()


cutpoint = namedtuple('cutpoint', ('point', 'polygon', 'ring'))


def cut_line_with_point(line, point):
    distance = line.project(point)
    pointlist = [(point.x, point.y)]
    for i, p in enumerate(line.coords):
        subdistance = line.project(Point(p))
        if subdistance >= distance:
            return (LineString(line.coords[:i] + pointlist),
                    LineString(pointlist + line.coords[i+(1 if subdistance == distance else 0):]))


def cut_polygon_with_line(polygon, line):
    polygons: List[List[LinearRing]] = [[polygon.exterior, *polygon.interiors]
                                        for polygon in assert_multipolygon(polygon)]

    points = deque()
    for i, polygon in polygons:
        for j, ring in polygon:
            intersection = ring.intersection(line)
            for item in getattr(intersection, 'geoms', (intersection, )):
                if isinstance(item, Point):
                    points.append(cutpoint(item, i, j))
                elif isinstance(item, LineString):
                    points.append(cutpoint(item.coords[0], i, j))
                    points.append(cutpoint(item.coords[-1], i, j))
                else:
                    raise ValueError

    points = deque(sorted(points, key=lambda p: line.project(p.point)))

    last = points.popleft()
    while points:
        current = points.popleft()
        if current.polygon == last.polygon:
            polygon = polygons[current.polygon]
            if current.ring != last.ring:
                ring1 = cut_line_with_point(polygon[last.ring], last.point)
                ring2 = cut_line_with_point(polygon[current.ring], current.point)
                new_ring = LinearRing(ring1[:-1] + ring1[0:] + ring2[:-1] + ring2[0:] + ring1[:1])
                if current.ring == 0 or last.ring == 0:
                    polygon[0] = new_ring
                    interior = current.ring if last.ring == 0 else last.ring
                    polygon[interior] = None
                    mapping = {interior: 0}
                else:
                    new_i = len(polygon)
                    mapping = {last.ring: new_i, current.ring: new_i}
                    polygon.append(new_ring)
                    polygon[last.ring] = None
                    polygon[current.ring] = None

                points = deque((cutpoint(item.point, item.polygon, mapping[item.ring])
                                if (item.polygon == current.polygon and item.ring in mapping) else item)
                               for item in points)
            elif current.ring == 0:
                new_i = len(polygons)
                exterior = cut_line_with_point(polygon[0], current.point)
                exterior = cut_line_with_point(LinearRing(exterior[:-1] + exterior[0:]), last.point)
                exterior1 = LinearRing(exterior[0][0:] + exterior[0][:1])
                exterior2 = LinearRing(exterior[1][0:] + exterior[1][:1])
                geom = Polygon(exterior1)
                polygon[0] = exterior1
                new_polygon = [exterior2]
                polygons.append(new_polygon)
                mapping = {}
                for i, interior in enumerate(polygon[1:]):
                    if not geom.contains(interior):
                        mapping[i] = len(new_polygon)
                        new_polygon.append(interior)

                points = deque((cutpoint(item.point, new_i, mapping[item.ring])
                                if (item.polygon == current.polygon and item.ring in mapping) else item)
                               for item in points)
                points = deque((cutpoint(item.point, new_i, 0)
                                if (item.polygon == current.polygon and item.ring == 0 and
                                    not exterior1.contains(item.point)) else item)
                               for item in points)

    return unary_union(tuple(Polygon(polygon[0], polygon[1:]) for polygon in polygons))
