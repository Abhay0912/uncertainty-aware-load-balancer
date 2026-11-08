import pytest

from lbsim.config import ServerSpec
from lbsim.estimators.service_time import ServiceTimeEstimator
from lbsim.forecasting.queue_projection import predict_completion
from lbsim.scheduling_view import make_server_views, task_request
from lbsim.server import build_servers
from lbsim.workload import Task


def task(i, work=1.0, cpu=1.0, mem=1.0, arrival=0):
    return Task(i, arrival, cpu, mem, work, task_class="short", estimated_work=work)


def test_scheduling_views_hide_oracle_work_and_remaining():
    server = build_servers((ServerSpec(2, 4, 1.0),))[0]
    server.assign(task(0, work=9.0), 0)
    request = task_request(task(1, work=7.0))
    view = make_server_views([server], 0)[0]
    assert not hasattr(request, "work")
    assert not hasattr(view.running[0], "remaining")
    assert not hasattr(view, "_running")


def test_projection_matches_fifo_head_of_line_blocking():
    server = build_servers((ServerSpec(2, 4, 1.0),))[0]
    server.assign(task(0, work=2.0, cpu=1.5), 0)
    server.assign(task(1, work=1.0, cpu=1.5), 0)
    server.assign(task(2, work=1.0, cpu=0.5), 0)
    candidate = task_request(task(3, work=1.0, cpu=0.5))
    prediction = predict_completion(
        make_server_views([server], 0)[0], candidate, 0, ServiceTimeEstimator()
    )
    assert prediction.status == "predicted"
    assert prediction.start_tick == 3
    assert prediction.finish_tick == 4


def test_infeasible_projection_is_explicit():
    server = build_servers((ServerSpec(2, 4, 1.0),))[0]
    prediction = predict_completion(
        make_server_views([server], 0)[0],
        task_request(task(1, cpu=3.0)),
        0,
        ServiceTimeEstimator(),
    )
    assert prediction.status == "infeasible"
    assert prediction.response_time == float("inf")
