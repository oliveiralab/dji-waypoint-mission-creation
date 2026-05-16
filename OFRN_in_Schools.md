# OFRN in Schools: Digital Stand Count Using Drones

## Program Overview

**OFRN in Schools: Digital Stand Count Using Drones** is an educational outreach
program that introduces K–12 and early-college students to applied drone
technology in agriculture. Students learn how unmanned aerial systems (UAS)
are used in modern crop scouting and compare traditional, manual stand count
methods against AI-powered digital analysis from drone imagery.

The program combines classroom instruction, hands-on field work, and a
computer lab session, giving students a complete view of a real precision-ag
workflow: **plan → fly → measure → analyze → compare**.

---

## Learning Objectives

By the end of the program, students will be able to:

- Explain what a drone is, how it flies, and the basics of safe operation.
- Describe what *stand count* is and why it matters to growers.
- Perform a manual stand count in the field using standard agronomic methods.
- Operate (or observe operation of) a drone collecting imagery over sampling
  points at a controlled height.
- Use a digital platform (Sentera FieldAgent) to upload imagery and generate
  an automated stand count report.
- Compare manual vs. digital counts and discuss accuracy, sources of error,
  and the value of each method.

---

## Program Structure

The program is delivered in **two parts**.

### Part 1 — Field Day

#### Session 1.1 — Drone & Flight Basics (1 hour, classroom)

A 1-hour interactive class covering:

- What is a drone? Components, sensors, and common platforms.
- How drones fly: lift, propulsion, GPS/RTK positioning.
- Drone uses in agriculture: scouting, mapping, spraying, stand counts.
- Safety, regulations (FAA Part 107 overview), and ethics.
- Introduction to the day's mission: planned flight path, sampling points,
  and what data we will collect.

#### Session 1.2 — Drone Flight Demonstration (field)

Instructors demonstrate the planned mission live:

- Pre-flight checklist and site walk-through.
- Take-off and execution of an automated waypoint mission over the field's
  sampling points.
- Explanation of altitude (85 ft AGL), gimbal angle (nadir / straight down),
  hover-and-photo behavior, and why these are kept consistent.
- Landing and post-flight review of captured images.

#### Session 1.3 — Manual Stand Count (field)

Students are split into small groups. Each group:

- Walks to assigned sampling points (the same points the drone photographed).
- Counts emerged plants in a measured row segment (standard agronomic
  protocol, e.g. 1/1000 acre row length).
- Records counts on a data sheet, with point ID, row spacing, and observer
  name.
- Discusses challenges: skips, doubles, weeds, edge effects.

> **Output of Part 1:** drone images at each sampling point + manual count
> ground-truth data.

---

### Part 2 — Lab Day

#### Session 2.1 — Digital Stand Count (computer lab)

Students move to a computer lab for the analysis phase.

- Overview of the digital stand count platform (**Sentera FieldAgent**):
  - What the platform does and how it uses computer vision / AI.
  - Required image properties: resolution, overlap, gimbal angle, GSD.
  - How the algorithm detects individual plants from nadir imagery.
- Each group of students:
  1. Logs into the platform.
  2. Uploads the drone images captured at *their* sampling points during the
     field day.
  3. Configures the analysis (crop type, row spacing, expected emergence).
  4. Runs the digital stand count.
  5. Generates and reviews the stand count report.

#### Session 2.2 — Compare & Discuss

- Each group enters their **manual count** and **digital count** for each
  sampling point into a shared spreadsheet.
- Class compares results:
  - Agreement and disagreement between methods.
  - Sources of error: human (mis-counting, fatigue) vs. algorithmic
    (lighting, weeds, image blur, GSD variation).
  - Operational trade-offs: time, labor, scalability, cost.
- Wrap-up discussion on careers and further learning paths in precision ag,
  drone operation, remote sensing, and data science.

---

## Equipment & Software

| Category | Item |
|---|---|
| Aircraft | DJI Matrice 4E (or comparable enterprise platform) |
| Controller | DJI RC Plus / Pilot 2 |
| Mission planning | `djikmz`-generated KMZ waypoint mission (terrain-corrected, constant 85 ft AGL) |
| Field tools | Measuring tape / hoop, tally counters, data sheets |
| Software | Sentera FieldAgent (digital stand count) |
| Computer lab | One workstation per student group, internet access, modern browser |

---

## Mission Settings (consistent across all flights)

To make manual and digital counts directly comparable, every flight uses the
same standardized settings:

- **Altitude:** 85 ft (25.9 m) above ground level — **terrain-corrected**
  per waypoint, so ground sample distance (GSD) is constant across the field.
- **Speed:** 5 m/s.
- **Hover:** 2 seconds at each waypoint before photo capture (eliminates
  motion blur and GPS micro-drift).
- **Gimbal:** −90° (nadir, straight down).
- **Heading:** fixed (aligned with planting rows when possible).
- **Action:** one photo per sampling point.

These settings are baked into [convert_to_dji.py](convert_to_dji.py), which
converts a KML of sampling points (with elevation) into a DJI-compatible
KMZ mission file.

---

## Safety

- Only certified pilots operate the aircraft. Students observe from a
  designated safe area during flight.
- All flights follow FAA Part 107 rules and any applicable institutional or
  landowner requirements.
- Pre-flight checklists, NOTAM checks, and weather (wind, visibility)
  assessments are completed before every flight.
- A clear chain of command and abort procedure is briefed before take-off.

---

## Assessment & Outcomes

Students are evaluated informally through participation and through the
manual-vs-digital comparison exercise. Expected outcomes include:

- Improved understanding of how drones support real-world agronomic
  decisions.
- Hands-on exposure to a complete precision-ag data pipeline.
- Familiarity with at least one industry tool (Sentera FieldAgent).
- Critical thinking about measurement accuracy and the role of automation.

---

## Acknowledgments

OFRN in Schools is delivered by the OFRN team and partner schools, with
support from agronomy, extension, and engineering faculty.
