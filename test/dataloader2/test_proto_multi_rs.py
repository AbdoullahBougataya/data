# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

import time
import unittest
from unittest import TestCase

from torchdata.dataloader2 import DataLoader2, PrototypeMultiProcessingReadingService

from torchdata.dataloader2.graph import list_dps, traverse_dps
from torchdata.datapipes.iter import IterableWrapper


class TestPrototypeMultiProcessingReadingService(TestCase):
    r"""
    This tests specific functionalities of PrototypeMultiProcessingReadingService, notably
    `pause`, `resume`, `snapshot`.
    """

    # Test DataPipes
    n_elements = 10
    dp1 = IterableWrapper(range(n_elements)).shuffle().sharding_filter()
    double_pause_dp = dp1.prefetch().prefetch()
    test_dps = [dp1, double_pause_dp]

    def test_reading_service_pause_resume_0_worker(self) -> None:

        # Functional Test: Verifies that this ReadingService will raise error when `pause/resume` is used
        #                  with `num_workers = 0`
        rs0 = PrototypeMultiProcessingReadingService(num_workers=0, worker_prefetch_cnt=0, main_prefetch_cnt=0)
        dl0: DataLoader2 = DataLoader2(self.dp1, reading_service=rs0)
        res0 = []
        for i, x in enumerate(dl0):
            res0.append(x)
            if i in {2}:
                with self.assertRaisesRegex(RuntimeError, r"pause"):
                    dl0.pause()
                with self.assertRaisesRegex(RuntimeError, r"resume"):
                    dl0.resume()

    def test_reading_service_pause_resume(self) -> None:

        for dp in self.test_dps:

            rs1 = PrototypeMultiProcessingReadingService(num_workers=1, worker_prefetch_cnt=0, main_prefetch_cnt=0)
            rs2 = PrototypeMultiProcessingReadingService(num_workers=1, worker_prefetch_cnt=0, main_prefetch_cnt=2)
            rs3 = PrototypeMultiProcessingReadingService(num_workers=2, worker_prefetch_cnt=0, main_prefetch_cnt=0)
            rs4 = PrototypeMultiProcessingReadingService(num_workers=2, worker_prefetch_cnt=2, main_prefetch_cnt=0)
            rs5 = PrototypeMultiProcessingReadingService(num_workers=2, worker_prefetch_cnt=0, main_prefetch_cnt=2)
            rs6 = PrototypeMultiProcessingReadingService(num_workers=2, worker_prefetch_cnt=2, main_prefetch_cnt=2)
            test_rss = [rs1, rs2, rs3, rs4, rs5, rs6]

            # Functional Test: Testing various configuration of DataPipe/ReadingService to ensure the pipeline properly
            #                  pauses and resumes
            for rs in test_rss:
                dl: DataLoader2 = DataLoader2(dp, reading_service=rs)
                res = []
                for i, x in enumerate(dl):
                    res.append(x)
                    if i in {2, self.n_elements - 2}:
                        dl.pause()
                        dl.resume()

                self.assertEqual(list(range(self.n_elements)), sorted(res))

    def test_reading_service_pause_stop_yield(self) -> None:

        # Functional Test: Confirms that `dl` will stop yielding elements after `_pause` is called
        rs7 = PrototypeMultiProcessingReadingService(num_workers=2, worker_prefetch_cnt=0, main_prefetch_cnt=1)
        # TODO: If DL doesn't handle pause, this hangs, because the main_loop prefetcher doesn't follow messages
        #       and will never reach the _pause condition
        rs8 = PrototypeMultiProcessingReadingService(num_workers=2, worker_prefetch_cnt=1, main_prefetch_cnt=0)
        # TODO: If DL doesn't handle pause, this yields 1 extra per worker, because we are popping from buffer
        rs9 = PrototypeMultiProcessingReadingService(num_workers=2, worker_prefetch_cnt=0, main_prefetch_cnt=0)

        test_rss2 = [rs7, rs8, rs9]
        for rs in test_rss2:
            dl: DataLoader2 = DataLoader2(self.double_pause_dp, reading_service=rs)
            res = []
            for i, x in enumerate(dl):
                res.append(x)
                if i in {2}:
                    dl.pause()
            self.assertEqual(3, len(res))

        # TODO: The note below is only relevant if DL2 doesn't handle pause directly.
        #       This hangs if `prefetcher.join` doesn't have a timeout
        #       1. `prefetch_data.run_prefetcher` switched to `False`, and so it enters finally clause
        #       The ideal behavior should be it pauses after yield and don't do anything...
        #       Investigate why it doesn't halt at `yield`?? It should
        #       2. This might be due to two prefetchers in a row, yield doesn't stop when the downstream requests

    # TODO: Next PR
    # def test_reading_service_snapshot(self) -> None:
    #     pass
    #
    # def test_dataloader2_snapshot(self) -> None:
    #     pass


if __name__ == "__main__":
    unittest.main()