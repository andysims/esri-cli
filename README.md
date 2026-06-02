# ArcGIS Management Toolkit (esri-cli)

This is a work-in-progress Python CLI tool designed to centralize ArcGIS administration tasks (Content, Groups, and User management) into a single, efficient CLI.

## Current Status

**Under Development.** This is currently a refactoring project. Most functionality is still being ported over from PowerShell scripts.

## Planned Features

* **Centralized Authentication:** One-time login to manage GIS resources.
* **Content Management:** Find, summarize, and audit items.
* **Group Administration:** Manage memberships and security audits.
* **User Management:** Handle user accounts, identify stale users, and audit sharing permissions.

## Setup

1. **Environment:** Ensure you have your `.env` file configured with your ArcGIS credentials.
2. **Dependencies:** Install the required libraries:
`pip install -r requirements.txt`
3. **Usage:** The tool will eventually be used via a single entry point:
`python main.py [module] [command] [options]`

## Contributing

Since this is in early stages, please feel free to poke around the `src/` folder to see how the logic is being consolidated. If you find a better way to handle a specific API call, pull requests are welcome.

---

*Note: This project is meant to eventually deprecate/run alongside (haven't decided which) the `Geo-DB-Toolkit/ArcGISManagement` PowerShell module.*