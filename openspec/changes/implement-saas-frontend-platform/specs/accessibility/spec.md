### Requirement: Accessible enterprise UI

The frontend SHALL meet basic accessibility and responsive UX requirements for a professional SaaS interface.

#### Scenario: Interactive states

- **WHEN** a user interacts with buttons, links, inputs, menus, or dialogs
- **THEN** focus, hover, loading, disabled, and error states are visible and understandable

#### Scenario: Error feedback

- **WHEN** an API request fails
- **THEN** the user sees a contextual error message
- **AND** the error is available to assistive technology through `role="alert"` or an equivalent pattern

#### Scenario: Icon usage

- **WHEN** icons are used in UI controls
- **THEN** they come from a consistent SVG icon set
- **AND** emoji are not used as UI icons

