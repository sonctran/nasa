# Resume bullets and interview notes

**Status: DRAFT for Son to edit into his own voice.** Every number was measured from the final build
(`site/assets/data/plan.json`, `pytest`, `docs/screenshots/report.json`). The code was written with
Claude Code under your direction, so say that plainly if asked: the bullets below describe what the
project does and what you directed, tested and can explain.

## Project title line

**Marswalk Ops: Route and Schedule Optimizer for Mars Surface Walks** | NASA Space Apps Challenge 2026 | Python, Google OR-Tools, JavaScript
Live: https://sonctran.github.io/nasa/ · Code: https://github.com/sonctran/nasa

## Three bullets (action + method + measured result)

- Built a decision-support tool that plans a 6-hour, two-astronaut Mars walk on real NASA terrain data; modeled stop selection as an orienteering problem and solved it to proven optimality with Google OR-Tools CP-SAT in under 20 ms per plan.
- Quantified schedule risk with a 20,000-run Monte Carlo simulation and ranked plans by on-time probability: the recommended plan keeps 26 of the 36 science points reachable in 6 hours at a 98.2 % on-time return, against 79.7 % for the maximum-science plan; sensitivity analysis showed task time, not walking distance, drives the risk.
- Implemented A* routing with a human-factors cost model (time, metabolic energy, terrain hazard) in Python and JavaScript, verified by 172 automated tests; the hazard-aware route cut time on steep or rough ground from 19.3 to 1.7 minutes for a 2-minute longer walk, and the web app re-plans in under half a second.

Shorter versions, if space is tight:

- Formulated and solved a prize-collecting routing problem (Google OR-Tools CP-SAT) to schedule science stops for a 6-hour Mars walk on real NASA terrain data; plans proven optimal in under 20 ms.
- Ran 20,000-run Monte Carlo risk analysis to pick the plan with the most science at a 95 % on-time target: 26 points at 98.2 %, vs 79.7 % for the maximum-science plan.
- Shipped a public web app with live re-planning (under 0.5 s) and 172 automated tests.

## 30-second interview pitch

"For the NASA Space Apps Challenge I built Marswalk Ops, a planning tool for a six-hour walk on Mars. I treated it as an operations problem. The route comes from a cost model of walking time, energy and terrain hazard on real NASA elevation data. Which science stops to visit is an orienteering problem that I solve exactly with Google OR-Tools. Then I run twenty thousand simulated walks to see how often the crew gets home on time. The interesting result was the trade-off: the plan with the most science only gets home on time 80 % of the time, so the tool recommends a plan with a little less science at 98 %. And the sensitivity analysis showed the risk comes from task time, not walking, which is the same lesson as in a factory: the schedule slips at the work stations, not in transport."

## Three likely questions

**1. Why did you use an exact solver and not a heuristic?**
The problem is small: at most six stops. An exact solver proves the answer is the best one, in a few milliseconds. I did try the OR-Tools routing heuristic first, and it missed the best plan in 2 of 10 random test cases, so I switched to CP-SAT and added a test that compares it with brute force on 25 random cases.

**2. How do you know the model is right?**
I do not claim it is right for Mars; nobody has walked there. I claim it is checked. A* gives exactly the same cost as Dijkstra. The walking model, with lunar gravity, predicts Apollo 14's uphill speed at 2.11 km/h against 2.13 measured. On a real Perseverance drive, 53 % of my planned path is within 25 m of the rover's, against 38 % for a straight line. A second drive was inconclusive, and the app says so. Every assumed value is labelled.

**3. What was the hardest trade-off?**
The 95 % safety bar. A 30-point plan scores 94.96 % with my main walking model and 95.9 % with a second model. I did not tune the model to pass. The tool recommends the 26-point plan and shows the 30-point plan as a close call, so the decision stays with a person.

## A fourth, about AI

**How much of this did you write yourself?**
I used Claude Code to write most of the code and to draft the documents, and I say so in the README and on the app's Methods page. My part was the problem framing, the mission and science choices, the decision rules (the 95 % bar, the science scores), reviewing results, and deciding what to keep or throw out. I can walk through any part of the method.
