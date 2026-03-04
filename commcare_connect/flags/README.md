# Release Toggles in CommCare Connect

Commcare Connect uses [django waffle](https://waffle.readthedocs.io/en/stable/) to manage feature release.

Waffle provides different tools to control access to a feature on the environment.

## Usage

Connect uses both [switches](https://waffle.readthedocs.io/en/stable/types/switch.html) and [flags](https://waffle.readthedocs.io/en/stable/types/flag.html).

- While _switches_ are used to turn a feature **on or off for everyone**, _flags_ are used to enable a feature for **specific users, groups, users meeting certain criteria** (such as being authenticated, or superusers).
- This allows for global releases, as well as targeted releases to specific users, organizations, opportunities, and/or programs.

## Expectations

- Switches and toggles should be as **short-lived** as possible, existing through the release, but removed once the feature is out.
- All switches and flags should have a **detailed description** in the note field of the model, describing the feature they control.

## Configuration Details

- Connect uses the django admin to manage the backend models and enable or disable switches and flags.
- Connect uses the `WAFFLE_CREATE_MISSING_SWITCHES` so that switches are automatically added to the database when they are encountered in the codebase (specifically when using `switch_is_active()`). However, manually adding them prior to deploy is preferred.
- For flags however, these will not automatically be added to the database (as the standard `flag_is_active()` waffle function will generally not be used). Rather, the custom `is_active_for()` method on the custom `Flag` model will be used, and flags should be created prior to deploy.
