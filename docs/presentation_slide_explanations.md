# Presentation Slide-by-Slide Explanation

This guide explains the presentation in simple, non-technical language.

## Slide 1 — Uncertainty-Aware Predictive Task Placement

This introduces the project. The system decides which cloud server should handle each incoming task.

The main idea is to predict how quickly each server can finish the task, rather than choosing a server only
because it currently appears lightly loaded.

## Slide 2 — Why task-aware placement?

Two servers can look similarly loaded but still finish a new task at very different times.

One may have a short queue and be able to finish the task quickly. Another may have a long queue or may not
have enough memory available. The project therefore looks at the specific task and the actual work waiting on
each server.

## Slide 3 — Architecture: predict, then select

The process has four simple stages:

1. Read the information a scheduler is allowed to see.
2. Estimate how long the new task may take.
3. Pretend to place the task on each possible server and see when it would finish.
4. Choose the server with the best predicted result.

The uncertainty-aware version also considers the possibility that the estimate may be wrong.

## Slide 4 — The shadow queue matches the simulator

The system creates a temporary copy of a server’s queue to test a possible assignment.

It follows the same rules as the real server:

- Existing tasks remain in order.
- A waiting task cannot jump over the task in front of it.
- CPU and memory must both be available.
- Finished tasks free their resources.
- New waiting tasks start at the correct time.

This makes the prediction consistent with what the simulator actually does.

## Slide 5 — Practical information contract

The scheduler can see normal operational information such as CPU demand, memory demand, queue length,
server speed, and a task’s estimated duration or category.

It cannot see the exact hidden amount of work or the exact future finish time. This is important because the
method should represent what a real scheduling system could reasonably know.

## Slide 6 — Matched experimental design

Every method is tested fairly:

- The same tasks are given to every method.
- The same five random seeds are used.
- Each run starts with fresh servers.
- The same 18-second response-time target is used.
- Results are compared seed by seed.

This means one method cannot win simply because it received an easier workload.

## Slide 7 — Policies compared

The project compares the proposed method with several common approaches:

- **Round Robin:** take turns between servers.
- **Random:** choose a server randomly.
- **Weighted Round Robin:** give more work to larger, faster servers.
- **Least CPU:** choose the server showing the lowest CPU use.
- **Weighted Metric:** consider CPU, memory, and recent response time together.
- **ECT-only:** choose the server predicted to finish the task earliest.
- **Uncertainty-aware ECT:** make the same prediction, but be more cautious when the prediction is uncertain.

## Slide 8 — Stable workload: ECT reduces tail latency

In the stable workload, the amount of incoming work changes gradually.

The completion-time approach produces a much better worst-case experience than most alternatives. Its 95th
percentile response time is about 14 seconds, and only about 1.6% of tasks miss the target.

This means it helps reduce the number of tasks that get stuck waiting unusually long.

## Slide 9 — Bursty workload: ECT improves latency and throughput

The bursty workload suddenly sends much more work for short periods.

No method can completely avoid delays when more work arrives than the whole cluster can process. However,
the completion-time approach still gives the lowest average and high-end response times in this experiment,
while completing more tasks per second than the other practical approaches.

## Slide 10 — Baseline policies versus ECT

This slide provides the main numerical comparison.

The important pattern is:

- Simple turn-taking and random selection create very large delays.
- Load-aware methods perform much better.
- Completion-time prediction has the strongest tail-latency results.
- The uncertainty adjustment does not consistently improve the basic completion-time prediction yet.

## Slide 11 — Uncertainty adds no consistent benefit yet

This is the controlled comparison between the two completion-time versions.

The basic version uses the expected finish time. The cautious version adds a penalty when the finish-time
estimate is less certain.

In the current experiment, the cautious version is slower on average and misses the target slightly more
often. It is therefore an interesting research direction, but not yet a proven improvement.

## Slide 12 — Why ECT is practical — and where it is limited

The method is practical because it uses information available when a task arrives, such as a duration estimate,
task category, queue, and resource availability.

Its results depend on the quality of those estimates. The experiments also use simulated workloads, so the
method still needs testing with more realistic data and monitoring conditions.

## Slide 13 — What the evaluation supports

The experiments support a careful conclusion:

> Predicting the completion time of the specific task is a promising way to improve server selection.

They do not yet prove that the uncertainty adjustment is always useful or that the method will perform the
same way in a production cloud system.

## Slide 14 — Takeaways

The three main lessons are:

1. A method that ignores queues and server capacity performs badly.
2. Predicting the finish time of the actual task improves placement decisions.
3. Being cautious about uncertainty is sensible, but the current results do not yet show a consistent benefit.

## Slide 15 — Thank you

This is the closing slide. It restates the central message:

> Choose a server using a realistic prediction based on what is known when the task arrives.

The presentation then opens the discussion for questions about the prediction method, fairness of the
experiments, and the results.
