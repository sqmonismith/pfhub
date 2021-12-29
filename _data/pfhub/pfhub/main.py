"""Tools for rendering the PFHub data.
"""

from functools import wraps
import glob
import os
from urllib.error import HTTPError, URLError
import pathlib

from toolz.curried import filter as filter_
from toolz.curried import map as map_
from toolz.curried import (
    get_in,
    curry,
    assoc,
    pipe,
    thread_first,
    do,
    get,
    compose,
    tail,
    merge_with,
    identity,
    valmap,
    juxt,
    second,
)
import numpy as np
import yaml
import pandas
import plotly.express as px
import plotly.graph_objects as go
from scipy.interpolate import griddata


BENCHMARK_PATH = str(
    pathlib.Path(__file__).resolve().parent / "../../simulations/*/meta.yaml"
)


def read_yaml(filepath):
    """Read a YAML file

    Args:
      filepath: the path to the YAML file

    Returns:
      returns a dictionary

    Test by reading from temporary test data

    >>> yaml_data = read_yaml(getfixture('yaml_data_file'))
    >>> assert yaml_data['benchmark']['id'] == '1a'

    """
    with open(filepath) as stream:
        data = yaml.safe_load(stream)
    return data


make_id = lambda x: ".".join([x["benchmark"]["id"], str(x["benchmark"]["version"])])

make_author = lambda x: pipe(
    x, get_in(["metadata", "author"]), get(["first", "last"]), " ".join
)


def read_add_name(yaml_path):
    """Add the name field to the meta.yaml data.

    The yaml files are located in
    .../pfhub/_data/simulations/name_of_result/meta.yaml. The name
    field, "name_of_result" is in the directory name and needs to be
    combined with the data.

    Args:
      yaml_path: the path to the YAML file

    Returns:
      a dictionary of the data in the YAML file along with the name of
      the result

    Test using temporary test data

    >>> assert read_add_name(getfixture('yaml_data_file'))['name'] == 'result'

    """
    return assoc(
        read_yaml(yaml_path), "name", os.path.split(os.path.split(yaml_path)[0])[1]
    )


def maybe(func):
    """Decorator to allow functions to have the maybe construct.

    A "maybe" function returns None if passed None.

    Args:
      func: the function to decorate

    Returns:
      the decorated function

    >>> @maybe
    ... def add1(x):
    ...     return x + 1

    >>> add1(None)
    >>> add1(1)
    2

    """

    @curry
    def wrapper(*args):
        if args[-1] is None:
            return None
        return func(*args)

    return wraps(func)(wrapper)


@maybe
def assign(columns, dataframe):
    """Curried version of assigning columns to a dataframe

    Args:
      columns: the new columns to append to the dataframe
      dataframe: dataframe to append to

    Returns:
      a new dataframe

    >>> assign(
    ...     dict(c=[5, 6]),
    ...     pandas.DataFrame(dict(a=[1, 2], b=[3, 4]))
    ... )
       a  b  c
    0  1  3  5
    1  2  4  6

    """
    return dataframe.assign(**columns)


def compact(items):
    """Remove None items from sequence

    Args:
      items: sequence to remove Nones from

    Returns:
      new sequence with no Nones

    >>> list(compact([1, None, 2]))
    [1, 2]

    """
    return filter(lambda x: x is not None, items)


def concat_items(items):
    """Assign new columns and then concatenate sequence of dataframes

    Args:
      items: sequence of tuples `[(x0, y0), ...]`. `x0` is a
        dictionary of new columns and `y0` are dataframes

    Returns:
      concatenated dataframes

    >>> x = pandas.DataFrame(dict(x=[1, 2]))
    >>> concat_items([(dict(z='z'), x)])
       x  z
    0  1  z
    1  2  z
    >>> x = pandas.DataFrame(dict(x=[1, 2]))
    >>> y = pandas.DataFrame(dict(y=[1, 2]))
    >>> concat_items([(dict(z='z'), x), (dict(), y)])
         x    z    y
    0  1.0    z  NaN
    1  2.0    z  NaN
    0  NaN  NaN  1.0
    1  NaN  NaN  2.0

    """
    return pipe(
        items, map_(lambda x: assign(x[0], x[1])), compact, list, maybe(pandas.concat)
    )


@curry
def update_column(func, columns, dataframe):
    """Apply function to columns in a dataframe

    Args:
      func: the function to apply
      columns: the columns to apply the function
      dataframe: the dataframe to change

    Returns:
      a new dataframe with updated columns

    >>> update_column(
    ...     lambda x: x + 1,
    ...     columns=('x',),
    ...     dataframe=pandas.DataFrame(dict(x=[1, 2], y=[1, 2]))
    ... )
       x  y
    0  2  1
    1  3  2

    """
    return dataframe.apply(lambda x: func(x) if x.name in columns else x)


def table_results(data):
    """Generate a simpler record for a table of data

    Args:
      data: data from a meta.yaml

    Returns:
      a flattened subset of the data suitable for a table of data

    >>> import datetime
    >>> expected = dict(
    ...     Name='result',
    ...     Code='code_name',
    ...     Benchmark='1a.1',
    ...     Author='first last',
    ...     Timestamp=datetime.date(2021, 12, 7)
    ... )
    >>> data = read_add_name(getfixture('yaml_data_file'))
    >>> assert table_results(data) == expected

    """
    return dict(
        Name=data["name"],
        Code=data["metadata"]["implementation"]["name"],
        Benchmark=make_id(data),
        Author=make_author(data),
        Timestamp=data["metadata"]["timestamp"],
    )


@curry
def get_yaml_data(benchmark_path, benchmark_ids):
    """Get all the simulation yaml data for the give benchmarks

    Args:
      benchmark_path: path to data file used by glob
      benchmark_ids: sequence of benchmark ids

    Returns:
      all the data for the given benchmarks

    >>> d = getfixture('test_data_path')
    >>> data = list(get_yaml_data(str(d.resolve()) + '/*/meta.yaml', ['1a.1', '2a.1']))
    >>> assert data[0]['name'] == 'result2'
    >>> assert data[1]['name'] == 'result1'

    """
    return pipe(
        benchmark_path,
        glob.glob,
        map_(read_add_name),
        filter_(lambda x: make_id(x) in benchmark_ids),
    )


@curry
def get_table_data(benchmark_ids, benchmark_path=BENCHMARK_PATH):
    """Get a Pandas DataFrame of result data

    Args:
      benchmark_ids: sequence of benchmark ids
      benchmark_path: path to data file used by glob

    Returns:
      Pandas DataFrame of data

    >>> d = getfixture('test_data_path')
    >>> p = str(d.resolve()) + '/*/meta.yaml'
    >>> get_table_data(['1a.1', '2a.1'], benchmark_path=p)
          Name       Code Benchmark      Author  Timestamp
    0  result2  code_name      2a.1  first last 2021-12-07
    1  result1  code_name      1a.1  first last 2021-12-07

    """
    return pipe(
        benchmark_ids,
        get_yaml_data(benchmark_path),
        map_(table_results),
        pandas.DataFrame,
        update_column(pandas.to_datetime, ["Timestamp"]),
    )


@curry
def get_result_data(data_names, benchmark_ids, keys, benchmark_path=BENCHMARK_PATH):
    """Get result data concatenated into a single DataFrame

    Args:
      data_names: the names of the data blocks
      benchmark_ids: sequence of benchmark ids
      keys: columns of each data item
      benchmark_path: path to data file used by glob

    Returns:
      Pandas DataFrame of concatenated data

    >>> d = getfixture('test_data_path')
    >>> get_result_data(
    ...     ['free_energy'],
    ...     ['1a.1', '2a.1'],
    ...     ['x', 'y'],
    ...     benchmark_path=str(d.resolve()) + '/*/meta.yaml',
    ... )
         x    y     data_set benchmark_id sim_name
    0  0.0  0.0  free_energy         2a.1  result2
    1  1.0  1.0  free_energy         2a.1  result2
    0  0.0  0.0  free_energy         1a.1  result1
    1  1.0  1.0  free_energy         1a.1  result1


    """
    return pipe(
        benchmark_ids,
        get_yaml_data(benchmark_path),
        map_(
            lambda x: (
                dict(benchmark_id=make_id(x), sim_name=x["name"]),
                get_data_from_yaml(data_names, keys, x),
            )
        ),
        concat_items,
    )


@curry
def get_data_from_yaml(data_names, keys, yaml_data):
    """Get data from a single meta.yaml

    Args:
      data_names: the names of the data blocks to extract
      keys: columns of each data item
      yaml_data: dictionary from a single meta.yaml

    Returns:
      DataFrame from the YAML data block

    >>> d = getfixture('test_data_path')
    >>> data = list(get_yaml_data(str(d.resolve()) + '/*/meta.yaml', ['1a.1', '2a.1']))

    >>> get_data_from_yaml(['free_energy'], ['x', 'y'], data[0])
         x    y     data_set
    0  0.0  0.0  free_energy
    1  1.0  1.0  free_energy

    """
    return pipe(
        yaml_data,
        get("data"),
        filter_(lambda x: x["name"] in data_names),
        map_(lambda x: (dict(data_set=x["name"]), read_vega_data(keys, x))),
        concat_items,
    )


@curry
def apply_transform(transform, values):
    """Apply a vega transform to a set of values

    This is an inplace operation. This was difficult to implement with
    "exec" without inplace.

    Args:
      transform: vega style transform as a dictionary
      values: the values to transform as a DataFrame

    >>> transform = {'type' : 'formula', 'expr' : '2 * datum.time', 'as' : 'x'}
    >>> df = pandas.DataFrame(dict(time=[0, 1, 2]))
    >>> apply_transform(transform, df)
    >>> df
       time  x
    0     0  0
    1     1  2
    2     2  4

    >>> apply_transform({'type' : 'blah'}, None)
    Traceback (most recent call last):
    ...
    RuntimeError: blah transform type is not supported

    """
    if transform["type"] == "formula":
        datum = values  # pylint: disable=unused-variable  # noqa: F841
        exec(  # pylint: disable=exec-used
            "values[transform['as']] = " + transform["expr"]
        )
    else:
        raise RuntimeError(f"{transform['type']} transform type is not supported")


@maybe
def apply_transforms(data, values):
    """Apply a series of Vega transforms to a set of values

    Args:
      data: the data block with the transforms
      values: the values to transform as a DataFrame

    Returns:
      returns a new set of values as a DataFrame

    >>> data_block = dict(transform=[
    ...     {'type' : 'formula', 'expr' : '2 * datum.time', 'as' : 'x'},
    ...     {'type' : 'formula', 'expr' : 'datum.energy / 2', 'as' : 'z'}
    ... ])
    >>> df = pandas.DataFrame(dict(time=[0, 1, 2], energy=[10, 20, 30]))
    >>> apply_transforms(data_block, df)
       time  energy  x     z
    0     0      10  0   5.0
    1     1      20  2  10.0
    2     2      30  4  15.0

    >>> apply_transforms(dict(), df)
       time  energy  x     z
    0     0      10  0   5.0
    1     1      20  2  10.0
    2     2      30  4  15.0

    """
    if "transform" in data:
        return thread_first(
            values, *list(map_(lambda x: do(apply_transform(x)), data["transform"]))
        )
    return values


def sep(data_format):
    r"""Determine separator based on file type

    Args:
      data_format: data format block from Vega spec

    Returns:
      file separator character

    >>> sep(None)
    ','
    >>> sep({'type': 'csv'})
    ','
    >>> sep({'type': 'tsv'})
    '\t'
    >>> sep({'type': 'csv', 'remove_whitespace': True})
    ',\\s+'
    >>> sep({'type': 'blah'})
    Traceback (most recent call last):
    ...
    RuntimeError: {'type': 'blah'} data format not supported
    """
    if data_format is None:
        return ","

    if data_format["type"] == "csv":
        if "remove_whitespace" in data_format and data_format["remove_whitespace"]:
            return r",\s+"
        return ","

    if data_format["type"] == "tsv":
        return "\t"

    raise RuntimeError(f"{data_format} data format not supported")


@curry
def read_csv(sep_, path):
    """Read CSV file with a specified separator

    Args:
      sep_: the separator character
      path: the path to the csv file

    Returns:
      File content as a DataFrame

    >>> read_csv(',', getfixture('csv_file'))
       x  y
    0  0  0
    1  1  1
    >>> read_csv(',', 'http://blah.csv')
    <urlopen error [Errno -2] Name or service not known> for http://blah.csv

    """

    try:
        return pandas.read_csv(path, sep=sep_, engine="python")
    except (HTTPError, URLError) as error:
        print(f"{error} for {path}")
        return None


def sequence(*args):
    """Compose functions in order

    Args:
      args: the functions to compose

    Returns:
      composed functions

    >>> assert sequence(lambda x: x + 1, lambda x: x * 2)(3) == 8
    """
    return compose(*args[::-1])


def read_vega_data(keys, data):
    """Read vega data given keys to exract

    Read a vega data block given the keys (or columns) to extract

    Args:
      keys: columns of each data item
      data: the data block with the given columns

    Returns:
      The data columns in a pandas DataFrame

    """
    read_url = sequence(
        get("url"),
        read_csv(sep(data.get("format"))),
        maybe(lambda x: x[list(data["format"]["parse"].keys())]),
    )

    read_values = sequence(get("values"), pandas.DataFrame)

    return pipe(
        data,
        read_url if "url" in data else read_values,
        apply_transforms(data),
        maybe(get(keys)),
    )


def line_plot(
    data_name,
    benchmark_id,
    layout=None,
    columns=("x", "y"),
    benchmark_path=BENCHMARK_PATH,
):
    """Generate a Plotly line plot from the benchmark data  # noqa: E501

    Args:
      data_name: the name of the data blocks
      benchmark_id: the benchmark_id
      layout: dictionary with "x", "y" and "title" keys to customize the plot
      columns: the columns to plot from the data blocks
      benchmark_path: path to data files (used by glob)

    >>> d = getfixture('test_data_path')
    >>> line_plot(
    ...     'free_energy',
    ...     '1a.1',
    ...     columns=('x', 'y'),
    ...     benchmark_path=str(d.resolve()) + '/*/meta.yaml',
    ... )
    Figure({
        'data': [{'hovertemplate': 'Simulation Result=result1<br>x=%{x}<br>y=%{y}<extra></extra>',
    ...
                   'yaxis': {'anchor': 'x', 'domain': [0.0, 1.0], 'title': {'text': 'y'}}}
    })

    """
    if layout is None:
        layout = dict()

    return pipe(
        get_result_data(
            [data_name], [benchmark_id], list(columns), benchmark_path=benchmark_path
        ),
        lambda x: px.line(
            x,
            x=columns[0],
            y=columns[1],
            color="sim_name",
            labels=dict(
                x=get("x", layout, default="x"),
                y=get("y", layout, default="y"),
                sim_name="Simulation Result",
            ),
            title=get("title", layout, default=""),
        ),
        do(lambda x: x.update_layout(title_x=0.5)),
    )


def levelset_plot(
    data, layout=None, columns=("x", "y", "z"), mask_func=lambda x: slice(len(x))
):
    """Generate a Plotly level set plot

    Args:
      data: extracted data as a data frame
      layout: dictionary with "x", "y" and "title" keys to customize the plot
      mask_func: function to apply to remove values (helps to reduce memory usage)

    >>> x, y = np.mgrid[-1:1:10j, -1:1:10j]
    >>> x = x.flatten()
    >>> y = y.flatten()
    >>> r = np.sqrt((x)**2 + (y)**2)
    >>> z = 1 - r
    >>> sim_name = ['a'] * len(x)
    >>> d = dict(x=x, y=y, z=z, sim_name=sim_name)
    >>> df = pandas.DataFrame(d)
    >>> levelset_plot(df, layout={'levelset' : 0.5})
    Figure({
        'data': [{'colorscale': [[0, 'rgb(229, 134, 6)'], [1, 'rgb(229, 134, 6)']],
    ...
                   'yaxis': {'range': [-1, 1], 'scaleanchor': 'x', 'scaleratio': 1}}
    })
    >>> df.z = df.z - 0.5
    >>> levelset_plot(df)
    Figure({
        'data': [{'colorscale': [[0, 'rgb(229, 134, 6)'], [1, 'rgb(229, 134, 6)']],
    ...
                   'yaxis': {'range': [-1, 1], 'scaleanchor': 'x', 'scaleratio': 1}}
    })

    """
    if layout is None:
        layout = dict()

    colorscale = lambda index: pipe(
        px.colors.qualitative.Vivid,
        lambda x: x[index % len(x)],
        lambda x: [[0, x], [1, x]],
    )

    get_contour = lambda df, name, counter: go.Contour(
        z=df[columns[2]],
        x=df[columns[0]],
        y=df[columns[1]],
        contours=dict(
            start=get("levelset", layout, 0.0),
            end=get("levelset", layout, 0.0),
            size=0.0,
            coloring="lines",
        ),
        colorbar=None,
        showscale=False,
        line_width=2,
        name=name,
        showlegend=True,
        colorscale=colorscale(counter),
    )

    update_layout = lambda fig: fig.update_layout(
        title=get("title", layout, ""),
        title_x=0.5,
        xaxis=dict(range=get("range", layout, [-1, 1]), constrain="domain"),
        yaxis=dict(
            scaleanchor="x",
            scaleratio=1,
            range=get("range", layout, [-1, 1]),
        ),
    )

    return pipe(
        data,
        lambda df: df[mask_func(df)],
        lambda x: x.groupby("sim_name"),
        enumerate,
        map_(lambda x: get_contour(df=x[1][1], name=x[1][0], counter=x[0])),
        list,
        go.Figure,
        do(update_layout),
    )


def make_grid(stepsx, stepsy):
    """Generate a grid using Numpy's mgrid

    Args:
      stepsx: [low, high], number of points in x direction
      stepsy: [low, high], number of points in y direction

    Returns:
      mesh-grid ndarrays all of the same dimensions

    >>> make_grid(([0.1, 0.9], 2), ([0.1, 0.3], 3))
    (array([[0.1, 0.1, 0.1],
           [0.9, 0.9, 0.9]]), array([[0.1, 0.2, 0.3],
           [0.1, 0.2, 0.3]]))

    """
    slice_ = lambda x, n: slice(x[0], x[1], n * 1j)
    grid_x, grid_y = np.mgrid[slice_(*stepsx), slice_(*stepsy)]
    return grid_x, grid_y


@curry
def interp(keys, stepsx, stepsy, dataframe):
    """Interpolate unstructured data to a grid

    Args:
      keys: columns in dataframe to use
      stepsx: [low, high], number of points in x direction
      stepsy: [low, high], number of points in y direction

    Returns:
      interpolated values

    >>> expected = [[0, 0.5], [0.25, 0.75], [0.5, 1], [0, 0], [0, 0 ]]
    >>> actual = interp(
    ...     ['x', 'y', 'z'],
    ...     ([0., 2.], 5),
    ...     ([0., 1.], 2),
    ...     pandas.DataFrame(dict(
    ...         x=[0, 1, 0, 1, 0.5],
    ...         y=[0, 0, 1, 1, 0.5],
    ...         z=[0, 0.5, 0.5, 1, 0.5])
    ...     )
    ... )
    >>> assert np.allclose(actual, expected)

    """
    return griddata(
        np.array([dataframe[keys[0]], dataframe[keys[1]]]).T,
        dataframe[keys[2]],
        make_grid(stepsx, stepsy),
        method="cubic",
        fill_value=0.0,
    )


@curry
def order_of_accuracy_values_(keys, stepsx, stepsy, dataframe):
    """Calculate order of accuracy from benchmark field data for a series
    of data items

    Args:
      keys: the column names to used (e.g. ['x', 'y', 'phase_field'])
      stepsx: [low, high], number of points in x direction
      stepsy: [low, high], number of points in y direction
      dataframe: dataframe with columns corresponding to the keys

    Returns:
      tuple of estimated grid spacings and L2 norms

    >>> def make_df(nx):
    ...     x, y = np.mgrid[0:1:(nx - 1) * 1j, 0:1:(nx - 1) * 1j]
    ...     x = x.flatten()
    ...     y = y.flatten()
    ...     return pandas.DataFrame(
    ...        dict(x=x, y=y, z=x * y, sim_name='sim1', data_set=nx)
    ...     )

    >>> out = order_of_accuracy_values_(
    ...     ('x', 'y', 'z'),
    ...     ([0, 1], 1000),
    ...     ([0, 1], 1000),
    ...     pandas.concat([make_df(10), make_df(20), make_df(40)])
    ... )

    >>> v = out['sim1']
    >>> accuracy = (np.log(v[1][-1]) - np.log(v[1][0])) / (
    ...     np.log(v[0][-1]) - np.log(v[0][0])
    ... )
    >>> assert accuracy > 2

    """

    effective_dx = lambda df: np.sqrt(cell_area(len(df)))
    cell_area = (
        lambda n: (stepsx[0][1] - stepsx[0][0]) * (stepsy[0][1] - stepsy[0][0]) / n
    )

    norm = curry(
        lambda ref, x: np.linalg.norm(x - ref, ord=2)
        * np.sqrt(cell_area(stepsx[1] * stepsy[1]))
    )
    clean = sequence(list, tail(-1), np.array)

    error = sequence(
        map_(interp(keys, stepsx, stepsy)),
        list,
        lambda x: map_(norm(x[0]), x),
        clean,
    )

    dx_clean = sequence(map_(effective_dx), clean)

    return pipe(
        dataframe.data_set,
        dataframe.groupby,
        map_(second),
        list,
        # data,
        map_(lambda x: x.groupby("sim_name")),
        map_(tuple),
        map_(dict),
        merge_with(identity),
        valmap(sequence(curry(sorted)(key=len, reverse=True), juxt((dx_clean, error)))),
    )


def plot_order_of_accuracy(
    dataframe,
    keys,
    stepsx=([0, 1], 1000),
    stepsy=([0, 1], 1000),
    layout=None,
):  # pragma: no cover
    """Plot an order of accuracy plots for a series of result uploads.

    Args:
      dataframe: dataframe with columns corresponding to the keys
      keys: the column names to used (e.g. ['x', 'y', 'phase_field'])
      stepsx: [low, high], number of points in x direction
      stepsy: [low, high], number of points in y direction
      layout: dictionary with "x", "y" and "title" keys to customize the plot
      benchmark_path: path to data files used by glob

    """
    if layout is None:
        layout = dict()

    make_order = lambda df: pandas.DataFrame(
        dict(x=df.x, y=df.x ** 2 * df.y[0] / df.x[0] ** 2, sim_name=r"Δx<sup>2</sup>")
    )

    return pipe(
        dataframe,
        order_of_accuracy_values_(keys, stepsx, stepsy),
        lambda x: x.items(),
        map_(lambda x: dict(x=x[1][0], y=x[1][1], sim_name=x[0])),
        map_(pandas.DataFrame),
        list,
        lambda x: pandas.concat(x + [make_order(x[0])]),
        lambda df: px.line(
            df,
            x="x",
            y="y",
            color="sim_name",
            log_x=True,
            log_y=True,
            labels=get("labels", layout, dict()),
        ),
        lambda x: x.update_layout(
            title=get("title", layout, ""),
            title_x=0.5,
        ),
    )
