# Task 003: Aquarius Plant Plus60 / AMled integration

Status: planned; awaiting owner protocol and function information. No driver,
release artifact, or physical-device test is supplied by Task 001.

## Objective

Implement an independently installable and versioned Home Assistant module for
the owner's Aquarius Plant Plus60 / AMled equipment, once the exact protocol,
supported functions, and authorized test procedure are established.

## Required input before implementation

- Confirmed model/controller details and the owner-approved integration target.
- Protocol documentation or authorized, sanitized protocol evidence, including
  transport, authentication, commands, responses, and error handling.
- The intended functions and their limits: only functions supported by evidence
  enter the implementation scope.
- A device test plan with explicit authorization for any physical control and a
  recovery procedure appropriate to an aquarium light.

Do not assume that a driver, packet capture, firmware image, account credential,
or reusable implementation exists. Do not scan the network, reverse engineer
outside the authorized scope, change firmware, or send trial control commands.

## Implementation and acceptance boundary

Start with protocol parsing and synthetic fixtures. The integration must use
the catalog contract, have its own version and compatibility metadata, preserve
other integrations, and run with Manager and the Mac off. Live commissioning
and physical device control require the separate approved Task 003 procedure.

Record unsupported or unverified functions explicitly. Successful fixture tests
do not establish hardware compatibility or safe aquarium operation.
