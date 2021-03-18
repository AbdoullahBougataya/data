import copy

import torch
import time
import datapipes
import dataloader.queue

from torch.utils.data import IterDataPipe, IterableDataset, functional_datapipe, non_deterministic


class EventLoop:
    '''
    Threading and multi-processing will require own versions of EventLoop,
    this POC version doesn't support it.
    '''
    enabled = True
    handlers = []
    loop_generators = None
    uid = 0
    stack = []
    depth = 0

    @classmethod
    def iteration(cls):
        if not cls.enabled or not len(cls.handlers):
            return
        if cls.loop_generators is None:
            cls.loop_generators = [iter(cls._loop_iterator())]
        if len(cls.loop_generators) < cls.depth+1:
            cls.loop_generators.append(iter(cls._loop_iterator()))
        try:
            cls.depth += 1
            next(cls.loop_generators[cls.depth - 1])
            cls.depth -= 1
        except Exception as e:
            print(e)
            raise

    @classmethod
    def _loop_iterator(cls):
        while True:
            loop_name = ''
            for handle, _handle_name, uid in cls.handlers:
                loop_name += ' ' + _handle_name + '_' + str(uid)
            print('running loop for', loop_name, cls.stack)
            dataloader.queue.LocalQueue.report()
            
            for handle, _handle_name, uid in cls.handlers:
                try:
                    if uid not in cls.stack:
                        stack_len = len(cls.stack)
                        cls.stack.append(uid)
                        print("Going inside of", stack_len, _handle_name)
                        value = next(handle)
                        print("Going out of", stack_len, _handle_name)
                        stack_copy = copy.deepcopy(cls.stack)
                        cls.stack.clear()
                        if stack_len:
                            for i in range(stack_len):
                                cls.stack.append(stack_copy[i])
                        yield value
                    else:
                        pass
                except Exception as e:
                    print(e)
                    raise
            print('----------------------------------------------- completed one loop at ', cls.depth)
            # time.sleep(5)
        
        

    @classmethod
    def add_handler(cls, handler, handle_name='unnamed'):
        cls.uid += 1
        cls.handlers.append((handler, handle_name, cls.uid))

# Turns IterDataPipe into two mp.Queues, terminates when getting StopIteration


def DataPipeToQueuesLoop(source_datapipe, req_queue, res_queue):
    if isinstance(source_datapipe, IterDataPipe):
        pipe_type = datapipes.iter
        protocol_type = dataloader.queue.IterDataPipeQueueProtocol
    else:
        pipe_type = datapipes.map
        protocol_type = dataloader.queue.MapDataPipeQueueProtocol

    torch.set_num_threads(1)
    # Stop EventLoop for MultiProcessing case
    EventLoop.enabled = False
    for _ in pipe_type.DataPipeBehindQueues(source_datapipe, protocol_type(req_queue, res_queue), blocking_request_get=True):
        pass

# Puts datapipe behind two (request, response) queues, adds Iterator to the EventLoop to process messages


def WrapDatasetToEventHandler(source_datapipe, dp_name='unnamed dataset', prefetch=False):
    if isinstance(source_datapipe, IterDataPipe):
        pipe_type = datapipes.iter
        protocol_type = dataloader.queue.IterDataPipeQueueProtocol
        is_iter = True
    else:
        pipe_type = datapipes.map
        protocol_type = dataloader.queue.MapDataPipeQueueProtocol
        is_iter = False

    source_datapipe = pipe_type.EnsureNonBlockingDataPipe(
        source_datapipe)

    request_queue = dataloader.queue.LocalQueue(name=dp_name + ' request')
    response_queue = dataloader.queue.LocalQueue(name=dp_name + ' response')
    protocol = protocol_type(request_queue,
                             response_queue)
    if prefetch and is_iter:
        loop_generator = pipe_type.PrefetcherDataPipeBehindQueues
    else:
        loop_generator = pipe_type.DataPipeBehindQueues

    handler = iter(loop_generator(source_datapipe, protocol))
    EventLoop.add_handler(handler, dp_name)
    datapipe = pipe_type.QueueWrapper(protocol)
    datapipe._wrapped_source_datapipe = source_datapipe
    return datapipe


def SpawnProcessForDataPipeline(multiprocessing_ctx, datapipe):
    req_queue = multiprocessing_ctx.Queue()
    res_queue = multiprocessing_ctx.Queue()
    process = multiprocessing_ctx.Process(
        target=DataPipeToQueuesLoop, args=(datapipe, req_queue, res_queue))
    return process, req_queue, res_queue


datapipes.iter.NonBlocking.register_not_available_hook(
    lambda: EventLoop.iteration())
datapipes.map.NonBlocking.register_not_available_hook(
    lambda: EventLoop.iteration())
