# ArcGIS Management Toolkit (esri-cli)
This is a Python tool designed to centralize ArcGIS administration tasks (Content, Groups, User management, and auditing) into a single CLI.

## Current Status
**Under Development.** This is somewhat of a refactoring project. Most functionality is still being ported over from PowerShell scripts.
 * **Functional:** main.py (main CLI entry point), Users, and Groups.
 * **Next Up:** Auditing, Utils (for exporting reports to CSV), and Content.

## Planned Features
 * **Centralized Authentication:** One-time login to manage GIS resources.
 * **Content Management:** Find, summarize, and audit items.
 * **Group Administration:** Manage memberships and security audits.
 * **User Management:** Handle user accounts, identify stale users, and audit sharing permissions.
 * **Platform Auditing:** Analyze groups, content, user activity, sharing permissions, and stale/inactive accounts.

## Setup
 1. **Environment:** Ensure you have your .env file configured with your ArcGIS credentials.
 2. **Dependencies:** Install the package:
   pip install . (or pip install -r requirements.txt)
 3. **Usage:** Once installed, you can leverage the CLI directly:
   * esri-cli --help
   * esri-cli user --help
   * esri-cli group --help

## Contributing
Since this is in early stages, please feel free to poke around the src/ folder to see how the logic is being consolidated. If you find a better way to handle a specific API call, pull requests are welcome.

*Note: This project is meant to eventually deprecate the geo-db-toolkit/ArcGISManagement PowerShell module.*
