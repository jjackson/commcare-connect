import sys
from datetime import datetime, timedelta


def display_seconds(seconds):
    return str(timedelta(seconds=int(round(seconds))))


def with_progress_bar(iterable, length=None, prefix="Processing", oneline=True, stream=None, offset=0):
    """Turns 'iterable' into a generator which prints a progress bar.

    :param oneline: Set to False to print each update on a new line.
        Useful if there will be other things printing to the terminal.
        Set to "concise" to use exactly one line for all output.
    :param offset: Number of items already/previously iterated.
    """
    if stream is None:
        stream = sys.stdout
    if length is None:
        if hasattr(iterable, "__len__"):
            length = len(iterable)
        else:
            raise AttributeError(f"'{type(iterable)}' object has no len(), you must pass in the 'length' parameter")

    granularity = min(50, length or 50)
    start = datetime.now()

    info_prefix = "" if oneline else f"{prefix} "

    def draw(position, done=False):
        overall_position = offset + position
        overall_percent = overall_position / length if length > 0 else 1
        dots = int(round(min(overall_percent, 1) * granularity))
        spaces = granularity - dots
        elapsed = (datetime.now() - start).total_seconds()
        percent = position / (length - offset) if length - offset > 0 else 1
        remaining = display_seconds((elapsed / percent) * (1 - percent)) if position > 0 else "-:--:--"

        print(prefix, end=" ", file=stream)
        print("[{}{}]".format("." * dots, " " * spaces), end=" ", file=stream)
        print(f"{overall_position}/{length}", end=" ", file=stream)
        print(f"{overall_percent:.0%}", end=" ", file=stream)
        if overall_position >= length or done:
            print(f"{datetime.now() - start} elapsed", end="", file=stream)
        else:
            print(f"{remaining} remaining", end="", file=stream)
        print(("\r" if oneline and not done else "\n"), end="", file=stream)
        stream.flush()

    if oneline != "concise":
        print(f"{info_prefix}Started at {start:%Y-%m-%d %H:%M:%S}", file=stream)
    should_update = step_calculator(length, granularity)
    i = 0
    try:
        draw(i)
        for i, x in enumerate(iterable, start=1):
            yield x
            if should_update(i):
                draw(i)
    finally:
        draw(i, done=True)
    if oneline != "concise":
        end = datetime.now()
        elapsed_seconds = (end - start).total_seconds()
        print(f"{info_prefix}Finished at {end:%Y-%m-%d %H:%M:%S}", file=stream)
        print(f"{info_prefix}Elapsed time: {display_seconds(elapsed_seconds)}", file=stream)


def step_calculator(length, granularity):
    """Make a function that caculates when to post progress updates

    Approximates two updates per output granularity (dot) with update
    interval bounded at 0.1s <= t <= 5m. This assumes a uniform
    iteration rate.
    """

    def should_update(i):
        assert i, "divide by zero protection"
        nonlocal next_update, max_wait, first_update
        now = datetime.now()
        if now > next_update or (first_update and i / twice_per_dot > 1):
            first_update = False
            rate = i / (now - start).total_seconds()  # iterations / second
            secs = min(max(twice_per_dot / rate, 0.1), max_wait)  # seconds / dot / 2
            next_update = now + timedelta(seconds=secs)
            if secs == max_wait < 300:
                max_wait = min(max_wait * 2, 300)
            return True
        return False

    # start with short delay to compensate for excessive initial estimates
    # first update happens after 10s or 1/2 dot, whichever occurs first
    first_update = True
    max_wait = 10
    twice_per_dot = max(length / granularity, 1) / 2  # iterations / dot / 2
    start = datetime.now()
    next_update = start + timedelta(seconds=max_wait)
    return should_update
