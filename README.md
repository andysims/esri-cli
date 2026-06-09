# ArcGIS Management Toolkit (esri-cli)

A Python command-line interface designed to centralize and automate ArcGIS administration, optimization, and auditing tasks across environments (ArcGIS Enterprise/Portal and Online).

## Current Status

**Functional Core.** The application architecture enforces a strict separation of concerns, routing user input through `main.py` via `typer` and executing backend logic via decoupled modules in `src/`.

* **Production-Tested** Centralized Authentication, User Management, Group Administration, and Platform Auditing.
* **Integrated Utilities:** Rich-text terminal output formatting and built-in reporting exports (CSV/TXT).
* **Future Scope:** Content management deep-dives and custom operational health metrics will be expanded iteratively as needs evolve.

## Core Features

* **Centralized Connection Factory (`src/auth.py`):** Handles profile-based authentication (`.env`) for both ArcGIS Online (AGOL) and ArcGIS Enterprise Portals.
* **User Management (`src/users.py`):** Look up user accounts, compile active detail profiles, and audit profile configurations.
* **Group Administration (`src/groups.py`):** Query group structures, manage user memberships, and audit group properties.
* **Platform Auditing (`src/audit.py`):** Operational safety sweeps including (but not limited to):
    * `whats-new`: Track newly added users, groups, and content items across a given timeframe.
    * `inactive`: Identify stale accounts that haven't logged in within a target number of days.
    * `license-usage`: Generate distribution counts of assigned user licenses.
* **Export Subsystem (`src/utils.py`):** Uniform flags across commands to pass internal data models directly into automated CSV or text reports.

## Setup

1.  **Environment Configuration:**
    Configure your `.env` file at the root directory with your target environment credentials (e.g., URLs, usernames, passwords).

2.  **Installation:**
    Install the package and its prerequisites (`arcgis`, `typer`, `rich`, `pandas`, `python-dotenv`):
    ```bash
    pip install .
    # Or alternatively: pip install -r requirements.txt
    ```

3.  **Command Execution:**
    The tool uses a multi-command sub-app architecture. Append `--env` (defaults to `agol`) to any command to swap targeting profiles:
    ```bash
    # Root help menu
    esri-cli --help

    # Domain management help menus
    esri-cli user --help
    esri-cli group --help
    esri-cli audit --help

    # Example operational commands
    esri-cli user find --email jdoe@example.com
    esri-cli audit whats-new --days 14 --export-csv
    esri-cli audit inactive-users --days 90 --env portal
    ```

## Contributing

Contributions are welcome! If you're looking to help expand the toolkit:

1. **Review the architecture:** Take a look at the domain modules inside `src/` to see how raw ArcGIS API responses are mapped to structured Python dataclasses.
2. **Submit a PR:** Pull requests optimizing performance, refining logic, or adding new domain sub-commands are highly encouraged.

Please open an issue first to discuss any major architectural changes before submitting a pull request.