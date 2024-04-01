#!/usr/bin/env python3
"""Quantum Tanner code search experiment."""

import hashlib
import multiprocessing
import os
import time
from collections.abc import Hashable, Iterator

from qldpc import abstract, codes


def get_deterministic_hash(*inputs: Hashable, num_bytes: int = 4) -> int:
    """Get a deterministic hash from the given inputs."""
    input_bytes = repr(inputs).encode("utf-8")
    hash_bytes = hashlib.sha256(input_bytes).digest()
    return int.from_bytes(hash_bytes[:num_bytes], byteorder="big", signed=False)


class CordaroWagnerCode(codes.ClassicalCode):
    """Cordaro Wagner code with a given block length."""

    def __init__(self, length: int) -> None:
        code = codes.ClassicalCode.from_name(f"CordaroWagnerCode({length})")
        codes.ClassicalCode.__init__(self, code)


class MittalCode(codes.ClassicalCode):
    """Modified Hammming code with a given block length."""

    def __init__(self, length: int) -> None:
        base_code = codes.HammingCode(3)
        if length == 4:
            code = base_code.shorten(2, 3).puncture(4)
        elif length == 5:
            code = base_code.shorten(2, 3)
        elif length == 6:
            code = base_code.shorten(3)
        else:
            raise ValueError(f"Unrecognized length for {self.name}: {length}")
        codes.ClassicalCode.__init__(self, code.matrix)


def get_small_groups(max_order: int = 20) -> Iterator[tuple[int, int]]:
    """Iterator over all finite groups by order and index."""
    for order in range(3, max_order + 1):
        for index in range(1, abstract.SmallGroup.number(order) + 1):
            yield order, index


def get_codes_and_args() -> Iterator[tuple[codes.ClassicalCode, int]]:
    """Iterator over classical code classes and arguments."""
    yield from ((codes.HammingCode(rr), rr) for rr in (2, 3))
    yield from ((CordaroWagnerCode(nn), nn) for nn in (3, 4, 5, 6))
    yield from ((MittalCode(nn), nn) for nn in (4, 5, 6))


def run_and_save(
    group_order: int,
    group_index: int,
    base_code: codes.ClassicalCode,
    base_code_id: str,
    sample: int,
    num_samples: int,
    num_trials: int,
    *,
    identify_completion: bool = False,
    silent: bool = False,
) -> None:
    """Make a random quantum Tanner code, compute its distance, and save it to a text file.

    Note: the multiprocessing module is handle SymPy PermutationGroup objects properly, so we must
    instead construct groups here from their identifying data.
    """
    group = abstract.SmallGroup(group_order, group_index)
    group_id = f"SmallGroup-{group_order}-{group_index}"

    if not silent:
        job_id = f"{group_id} {base_code_id} {sample}/{num_samples}"
        print(job_id)

    seed = get_deterministic_hash(group_order, group_index, base_code.matrix.tobytes(), sample)
    code = codes.QTCode.random(group, base_code, seed=seed)

    code_params = code.get_code_params(bound=num_trials)
    if not silent:
        completion_text = ""
        if identify_completion:
            completion_text += f" ({job_id})"
        completion_text += f" code parameters: {code_params}"
        print(completion_text)

    headers = [
        f"distance trials: {num_trials}",
        f"code parameters: {code_params}",
    ]
    file = f"qtcode_{group_id}_{base_code_id}_s{seed}.txt"
    path = os.path.join(save_dir, file)
    code.save(path, *headers)


if __name__ == "__main__":
    num_samples = 100  # per choice of group and subcode
    num_trials = 1000  # for code distance calculations

    # the directory in which we're saving data files
    save_dir = os.path.join(os.path.dirname(__file__), "quantum_tanner_codes")

    # multiprocessing options
    max_concurrent_tasks = os.cpu_count() or 1
    timeout = 0.1  # seconds to wait before re-checking whether we can run start another task

    active_tasks: list[multiprocessing.pool.AsyncResult[None]] = []
    with multiprocessing.Pool(processes=max_concurrent_tasks) as pool:

        for group_order, group_index in get_small_groups():

            for base_code, code_param in get_codes_and_args():
                base_code_id = f"{base_code.name}-{code_param}"

                if group_order < base_code.num_bits:
                    # the code is too large for this group
                    continue

                for sample in range(num_samples):

                    # wait until we can start anot another task
                    while len(active_tasks) >= max_concurrent_tasks:
                        active_tasks = [task for task in active_tasks if not task.ready()]
                        time.sleep(timeout)

                    args = (
                        group_order,
                        group_index,
                        base_code,
                        base_code_id,
                        sample,
                        num_samples,
                        num_trials,
                    )
                    kwargs = dict(identify_completion=max_concurrent_tasks > 1)
                    task = pool.apply_async(run_and_save, args, kwargs)
                    active_tasks.append(task)

        # wait for all tasks to complete
        for task in active_tasks:
            task.wait()
