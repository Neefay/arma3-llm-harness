# Commander Mode: formal model

The concepts of commander mode and the rules between them, independent of engine and implementation. Conformance with the code is tested by `host/tests/test_model_doc.py`.

## 1. The loop

```mermaid
flowchart LR
  T[Truth] -->|perceive| K[Knowledge]
  K -->|speak| U[Utterance]
  U -->|hear| B[Belief]
  B -->|decide| A[Act]
  A -->|act| T
  T -.->|verdict| U
```

| Arrow | Signature | Owner | Error class |
|---|---|---|---|
| `perceive` | `Truth × Station → Knowledge` | Engine | Fog |
| `speak` | `Knowledge × Memory × Register → Utterance*` | Harness | Fault |
| `hear` | `Belief × Utterance → Belief` | Records, commander | Fault in the records, judgement in the reading |
| `decide` | `Belief → Act*` | Commander | Judgement |
| `act` | `Act × Truth → Truth` | Harness, engine | Fault |
| `verdict` | `Truth → Utterance` | Higher | Fault |

**Attribution.** An outcome is attributed to the first arrow, from `Truth`, whose output doesn't follow from its input. `Truth` reaching `Belief` by no arrow is a **leak**, and a fault. Fog and judgement are kept. Faults are removed.

```text
A | B   one of        A × B   both        A*   any number        A?   optional
```

## 2. Strata

```text
Stratum ::= Truth | Knowledge(Station) | Belief | Record
```

- **S1.** `Belief` changes only by `hear`, or by the commander's own `Act`.
- **S2.** `speak` reads only the station's `Knowledge`, its own orders, and handles (section 5).
- **S3.** Nothing in `Record` reaches `Belief`.
- **S4.** The result of issuing an order is independent of `Truth`.

## 3. Agents

```text
Agent   ::= Commander | Station | Higher | System | Operator | World
Station  =  Callsign × Member* × Leader          Leader: a slot, filled from Member*
```

| Agent | Addressable | Speaks | Fallible |
|---|---|---|---|
| Commander | | | Yes |
| Station | Yes | Yes | About the world |
| Member | No | Through its station | |
| Higher | No | Objectives and the end | No |
| System | No | Loss of the game, restart | No |
| Operator | No | No | |
| World | No | No | |

A station outlives its members. A session is bound to one battle.

## 4. Members

```text
Condition ::= Able | Down | Dead
Custody   ::= Lying(Place) | Carried(Member) | Aboard(Vehicle) | Treated(Member)     defined iff Down
Fate      ::= Up | Dead | Unknown
```

```mermaid
flowchart TD
  N[Nominal] -->|⊇| L[Living]
  L -->|⊇| A[Able]
  A -->|⊇| F[Free]
  A -->|⊇| P[Present]
```

| Set | Definition |
|---|---|
| `Nominal` | initial members ∪ joined members |
| `Living` | `{m ∈ Nominal \| Condition(m) ≠ Dead}` |
| `Able` | `{m ∈ Living \| Condition(m) = Able}` |
| `Free` | `{m ∈ Able \| on foot ∧ ¬Busy(m)}` |
| `Present` | `{m ∈ Able \| Riding(m) ∨ d(m, Leader) ≤ 100 m}` |

- **M1.** Every count names its set.
- **M2.** A casualty has at most one custody at a time.
- **M3.** A casualty's `Fate` is `Unknown` to everyone out of sight of him.

```text
Asset ::= Vehicle(Seat*) | Gun(Seat*, Ammo) | Facility          a vehicle may also be a facility
```

## 5. Names

```text
Handle(T)  = an identifier on the commander's list
Listing(T) = Handle(T) × Belief(T) × Time
```

| Handle | Denotes | Issued when |
|---|---|---|
| `Alpha` | Station | Scenario |
| `V1` | Vehicle, gun | Scenario, or sighted |
| `B1` | Structure | Scenario |
| `C1` | Casualty | Reported down |
| `A1` | Facility | Built |
| `O1` | Marker | Commander, or scenario |

- **N1.** A listing holds what was last said, and its time.
- **N2.** Fire is directed by `Grid` only.

## 6. Speech

```text
Utterance   =  Speaker × Addressee × Mode × Content × Precedence × Time
Content    ::= Task | Contact | OwnForce | Assets | Effects | Place
Trigger    ::= Change | Question
Register   ::= Calm | InCombat
Precedence ::= Flash | Priority | Routine
```

| Mode | Basis | Fallible |
|---|---|---|
| Commitment | Its own order | No |
| Self-report | Its own members and assets | Rarely |
| Observation | `Knowledge` of the world | Yes |
| Projection | Measured rates | Yes, bounded: "about", "at least" |
| Refusal | Inability | No |
| Verdict | `Truth` | No |
| Procedure | The net | No |

**Register.** `InCombat ⇔` fresh contact ∨ suppression ≥ θ ∨ recent loss ∨ shelling nearby. In combat, a station withholds its own grid, delays speech in proportion to suppression, defers answers, and gives projections as lower bounds.

**Quantisation.** Every quantity is spoken at a stated resolution.

| Quantity | Resolution |
|---|---|
| Own position | 100 m grid |
| Bearing | 5°, with error |
| Range | 50 m steps to 500 m, 100 m steps to 1,500 m, then "distant" |
| Count | one, a couple, a few, about N, a dozen, many |
| Ammunition | green, amber, red, black |
| Own members apart | distance and compass point |
| Duration | minutes |

- **U1.** An unprompted utterance wakes the commander. A reply, a deferral, and an unchanged check-in don't.
- **U2.** Every unprompted utterance has a threshold or a repeat limit.

## 7. Tasks

### 7.1 Properties

```text
Lane        ::= Course | Detail | Guns | Settings
Ending      ::= Finite | Triggered | Standing | Instant
Claims       =  the members a task requires
Realisation  =  the engine mechanism; non-normative
```

| Lane | Concurrency |
|---|---|
| Course | One per station |
| Detail | Any number |
| Guns | One per gun |
| Settings | Not a task |

### 7.2 Orders

<!-- order-table -->
| Order | Lane | Ending | Claims | Realisation |
|---|---|---|---|---|
| `MOVE` | Course | Finite | All | Waypoint |
| `SEARCH` | Course | Finite | All | Waypoint |
| `CLEAR` | Course | Finite | All | Scripted |
| `MOUNT` | Course, or Detail with a seat | Finite | On foot, or one | Scripted |
| `DISMOUNT` | Course | Finite | Aboard | Scripted |
| `SENTRY` | Course | Triggered | All | Waypoint |
| `HOLD` | Course | Standing | All | Waypoint |
| `PATROL` | Course | Standing | All | Waypoint |
| `OCCUPY` | Course | Standing | All | Placing |
| `CORDON` | Course | Standing | All | Placing |
| `ATTACK` | Course | Standing | All | CBA |
| `DEFEND` | Course | Standing | All | CBA |
| `PATROL_AREA` | Course | Standing | All | CBA |
| `SWEEP` | Course | Standing | All | CBA |
| `HALT` | Course | Instant | All | Engine |
| `CARRY` | Detail | Finite | Free, one per casualty | Scripted |
| `TREAT` | Detail | Finite | Medics | Scripted |
| `AID_POST` | Detail | Finite | A medic | Scripted |
| `UNLOAD` | Detail | Finite | None | Scripted |
| `FIRE_MISSION` | Guns | Finite | Crew | Engine |
| `CHECK_FIRE` | Guns | Instant | Crew | Engine |
| `POSTURE` | Settings | Instant | None | Engine |

`All` is every member not crewing a gun.

### 7.3 Claims

- **C1.** A Course task is entitled to `All`. A Detail is entitled only to `Free` members. A casualty belongs to at most one task.
- **C2.** A task ends `Superseded` when a newer task takes a member it requires.

Consequence: a Course order supersedes the station's Details, and a Detail never supersedes anything.

### 7.4 Plans

```text
Plan ::= Task | Task ; Plan
Task ::= Trip(Waypoint+) | Order
```

- **P1.** Every step before the last is `Finite` or `Triggered`, including every waypoint of a trip.
- **P2.** `Instant` orders are single-step plans.
- **P3.** A station has at most one plan, in its Course lane. A Course order replaces it, and the station says what was dropped.
- **P4.** A plan is validated whole when issued. Each step starts when the one before it has ended `Done` or `Moot`, and a `Failed` step ends the plan.

```text
Rule     = Trigger × Act
Trigger ::= At(time) | After(duration) | Every(duration) | Finished(step)
Act     ::= Directive | Query | Wake
```

### 7.5 Life of a task

```mermaid
stateDiagram-v2
  [*] --> Sent
  Sent --> Received
  Received --> Active
  Active --> Active: milestone
  Active --> Done
  Active --> Moot
  Active --> Failed
  Active --> Superseded
  Active --> Silent
  Done --> [*]
  Moot --> [*]
  Failed --> [*]
  Superseded --> [*]
  Silent --> [*]
```

| Outcome | Meaning |
|---|---|
| `Done` | Completed |
| `Moot` | Its subject died or recovered |
| `Failed` | Impossible |
| `Superseded` | Its members were claimed (C2) |
| `Silent` | No one left to report |

- **T1.** Only `Silent` ends a task without an utterance.

## 8. Time

```text
Clock     = mission time
Attention = Turn*
Turn      = Wake × Briefing × Act* × End
Wake     ::= Timer | Messages | Notice
Briefing  : Belief × Utterance* → Text
```

- **Ti1.** Mission time doesn't wait for the commander.
- **Ti2.** `Briefing` is a function of records alone, so any session can resume a battle.
- **Ti3.** A turn ends with a timer set, or with an explicit choice to wait for messages.

## 9. Scenarios

```text
Scenario  = Station* × Asset* × Enemy* × Objective* × Failure? × TimeLimit × Event* × Dial*
Objective = Text × Predicate(Truth)
```

| Predicate | Holds iff |
|---|---|
| `AllAt(S, p, r, foot)` | `∀ m ∈ Living(S): d(m, p) ≤ r`, and if `foot`, `Living(S) = Able(S)` and none riding, and `Able(S) ≠ ∅` |
| `Eliminated` | `Able(Enemies) = ∅` |
| `Reached(s, p, r)` | `d(pos(s), p) ≤ r`, where `pos(s)` is the position of an `Able` member of `s` |
| `Lost` | `∀ s: Able(s) = ∅` |

- **O1.** An objective is confirmed when its predicate holds at the end of a grace period, and is re-evaluated until then.
- **O2.** Predicates count own members by `Living`, and enemies by `Able`: an enemy who is down is out, and an own member who is down is not.

## Appendix: state machines

Each machine as it is held in the code. A quoted state is the code's own string.

### Game side

<!-- machine: carry -->
```mermaid
stateDiagram-v2
  state "going" as going
  state "fetching" as fetching
  state "lifting" as lifting
  state "carrying" as carrying
  state "working" as working
  state "loading" as loading
  state "done" as done
  [*] --> going: CARRY
  going --> going: next approach
  going --> lifting: reached
  going --> fetching: closest reachable
  going --> done: unreachable
  fetching --> lifting: 8 s
  lifting --> carrying: 9 s
  carrying --> loading: at vehicle
  carrying --> working: stalled within 60 m
  carrying --> done: at place, or stalled beyond 60 m
  working --> loading: 8 s, to a vehicle
  working --> done: 8 s, to a place
  loading --> done: aboard, or 5 s
  done --> [*]
  note right of done: from any state but loading, on carrier down, casualty dead or up, or superseded
```

<!-- machine: treat -->
```mermaid
stateDiagram-v2
  state "going" as going
  state "working" as working
  [*] --> queued: TREAT
  queued --> waiting: aboard or carried
  waiting --> queued: released
  queued --> going: medic free
  queued --> [*]: dead, up, or no medic left
  going --> going: next approach
  going --> working: reached
  going --> [*]: unreachable
  going --> queued: medic down
  working --> queued: medic down
  working --> [*]: up
```

<!-- machine: post -->
```mermaid
stateDiagram-v2
  state "going" as going
  state "building" as building
  [*] --> going: AID_POST
  going --> building: arrived
  going --> [*]: unreachable
  building --> [*]: built
```

<!-- machine: fire -->
```mermaid
stateDiagram-v2
  state "unable" as unable
  state "firing" as firing
  state "holding" as holding
  state "done" as done
  state "out" as out
  state "cantlay" as cantlay
  state "gunner" as gunner
  state "destroyed" as destroyed
  state "stopped" as stopped
  state "checked" as checked
  [*] --> unable: no gun, gunner, ammo or range
  [*] --> firing: FIRE_MISSION
  firing --> holding: no shot for 10 s
  holding --> firing: shot
  firing --> done: all fired
  firing --> out: ammo exhausted
  firing --> cantlay: no shot for 15 s, ready
  firing --> gunner: gunner not able
  firing --> destroyed: gun destroyed
  firing --> stopped: CHECK_FIRE
  holding --> stopped: CHECK_FIRE
  [*] --> checked: CHECK_FIRE record
```

<!-- machine: boarding -->
```mermaid
stateDiagram-v2
  state "going" as going
  state "on" as on
  state "taken" as taken
  state "nobody" as nobody
  state "noseat" as noseat
  state "unreachable" as unreachable
  state "wrecked" as wrecked
  state "none" as none
  state "going off" as going_off
  state "off" as off
  state "stuck" as stuck
  state "stopped" as stopped
  [*] --> going: MOUNT
  [*] --> wrecked: vehicle destroyed
  [*] --> noseat: no such seat
  [*] --> taken: no free seat
  [*] --> nobody: no one free
  going --> on: all aboard
  going --> taken: seat taken
  going --> nobody: none aboard
  going --> unreachable: deadline
  going --> wrecked: vehicle destroyed
  going --> stopped: Course order
  [*] --> going_off: DISMOUNT
  [*] --> none: DISMOUNT, none aboard
  going_off --> off: all off
  going_off --> stuck: 30 s
```

<!-- machine: clearing -->
```mermaid
stateDiagram-v2
  [*] --> between: CLEAR
  between --> inside: next building
  between --> between: ruin, skipped
  inside --> inside: next position to a free member
  inside --> between: all positions visited
  between --> [*]: none left
```

<!-- machine: placing -->
```mermaid
stateDiagram-v2
  [*] --> moving: OCCUPY or CORDON
  moving --> placed: all free members ready, or 90 s
  placed --> [*]: next Course order
```

<!-- machine: cba-task -->
```mermaid
stateDiagram-v2
  [*] --> running: ATTACK, DEFEND, PATROL_AREA, SWEEP
  running --> releasing: next order
  releasing --> [*]: 150 s
```

<!-- machine: custody -->
```mermaid
stateDiagram-v2
  [*] --> free
  free --> carried: carry starts
  carried --> free: carry ends
  free --> treated: treatment starts
  treated --> free: treatment ends
```

<!-- machine: busy -->
```mermaid
stateDiagram-v2
  [*] --> free
  free --> busy: assigned to a Detail
  busy --> free: Detail ends, member down, or superseded
```

### Host side

<!-- machine: battle -->
```mermaid
stateDiagram-v2
  [*] --> not_ready
  not_ready --> ready: first report
  ready --> running: mission started
  running --> ended: objectives met, time limit, or lost
  running --> restarted: mission restarted
  ended --> [*]
  restarted --> [*]
```

<!-- machine: attention -->
```mermaid
stateDiagram-v2
  [*] --> waiting
  waiting --> debouncing: message
  debouncing --> in_turn: quiet, ceiling, or notice
  waiting --> in_turn: timer or notice
  in_turn --> waiting: turn ended
  in_turn --> waiting: idle, assumed over
```

<!-- machine: chain -->
```mermaid
stateDiagram-v2
  [*] --> sent: plan validated, step 1 issued
  sent --> seen: step received
  seen --> sent: step Done or Moot, next issued
  seen --> [*]: step Failed
  seen --> [*]: last step issued
  sent --> [*]: superseded
  seen --> [*]: superseded
```

<!-- machine: objective -->
```mermaid
stateDiagram-v2
  [*] --> not_met
  not_met --> met: predicate holds
  met --> not_met: predicate fails
  met --> confirmed: grace elapsed
  confirmed --> [*]
```

<!-- machine: order -->
```mermaid
stateDiagram-v2
  [*] --> acknowledged
  acknowledged --> under_way
  acknowledged --> unable: impossible
  under_way --> under_way: passing a waypoint
  under_way --> arrived: last waypoint
  under_way --> on_station: HOLD or SENTRY in reach
  under_way --> in_position: placed
  under_way --> on_objective: CBA task in reach
  under_way --> finished: CLEAR done
  under_way --> stuck: no progress for 2 min
  stuck --> under_way: progress
```

<!-- machine: contact -->
```mermaid
stateDiagram-v2
  [*] --> none
  none --> in_contact: fresh contact
  in_contact --> in_contact: grouping changed
  in_contact --> none: nothing fresh for 120 s
```

<!-- machine: casualty-list -->
```mermaid
stateDiagram-v2
  [*] --> listed: reported down
  listed --> listed: relocated by report
  listed --> gone: up, or seen dead
  gone --> listed: down again
```

<!-- machine: apart -->
```mermaid
stateDiagram-v2
  [*] --> with_squad
  with_squad --> apart: beyond 100 m, not busy
  apart --> reported: 30 s
  apart --> with_squad: within 50 m
  reported --> with_squad: within 50 m
  apart --> [*]: down or aboard
  reported --> [*]: down or aboard
```

<!-- machine: outbox -->
```mermaid
stateDiagram-v2
  [*] --> said: calm, nothing queued
  [*] --> held: in combat, or queued behind
  held --> said: delay elapsed
  held --> [*]: mission ended or restarted
```

<!-- machine: server -->
```mermaid
stateDiagram-v2
  [*] --> none
  none --> loaded: battle set up
  loaded --> replaced: battle replaced or stopped
  replaced --> [*]
```
