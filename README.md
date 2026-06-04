# ArcGIS Management Toolkit (esri-cli)

This is a work-in-progress Python tool designed to centralize ArcGIS administration tasks (Content, Groups, User management, and auditing) into a single, efficient CLI.

## Current Status

**Under Development.** This is currently a refactoring project. Most functionality is still being ported over from PowerShell scripts.

## Planned Features

* [**Centralized Authentication:**](src/auth.py) One-time login to manage GIS resources.
* [**Content Management:**](src/content.py) Find, summarize, and audit items.
* [**Group Administration:**](src/groups.py) Manage memberships and security audits.
* [**User Management:**](src/users.py) Handle user accounts, identify stale users, and audit sharing permissions.
* [**Platform Auditing:**](src/audit.py) Analyze groups, content, user activity, sharing permissions, and stale/inactive accounts.

## Setup

1. **Environment:** Ensure you have your `.env` file configured with your ArcGIS credentials.
2. **Dependencies:** Install the required libraries:
`pip install -r requirements.txt`
3. **Usage:** The tool will eventually be used via a single entry point:
`python main.py [module] [command] [options]`

## Contributing

Since this is in early stages, please feel free to poke around the `src/` folder to see how the logic is being consolidated. If you find a better way to handle a specific API call, pull requests are welcome.

---

*Note: This project is meant to eventually deprecate the `geo-db-toolkit/ArcGISManagement` PowerShell module.*