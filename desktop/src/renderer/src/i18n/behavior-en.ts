/** Behavior copy aligned with behavior-zh. */
export const behaviorEn = {
	sessionDefaults: "Session defaults",
	sessionDefaultsHint: "Starting settings for each new conversation.",
	mode: "Default mode",
	modeHint:
		"Agent handles ordinary tasks. Plan prepares a proposal. Goal continues toward an objective. Mode and permission policy are configured separately.",
	modes: { agent: "Agent", plan: "Plan", goal: "Goal" },
	permissions: "Permission mode",
	permissionsHint:
		"Uses Harness Confirm, YOLO and Human policies. Confirm requests approval, YOLO runs actions without individual confirmation, and Human accepts commands you enter.",
	permissionModes: { confirm: "Ask each time", yolo: "Automatic", human: "Human control" },
	shell: "Command shell",
	shellHint:
		"Choose the desired interpreter. The current local Harness uses Bash; PowerShell options are frontend preferences pending execution-service support and availability checks. Sandboxes use their own shell.",
	shells: {
		system: "System default",
		"windows-powershell": "Windows PowerShell",
		pwsh: "PowerShell 7",
		"git-bash": "Git Bash",
		bash: "Bash",
		zsh: "Zsh",
	},
	frontendNotice:
		"Saved in this app's local frontend. Harness execution is not connected; these choices do not change active sessions or start sandboxes.",
	storageError: "Could not save locally. Your choices remain available for this app run.",
	sandbox: {
		title: "Sandbox",
		caption: "Configure isolated environments for tasks.",
		add: "Add profile",
		edit: "Edit profile",
		name: "Profile name",
		engine: "Isolation engine",
		engineHint:
			"Docker uses local Linux containers. Bubblewrap requires namespaces on Linux or WSL. Saving does not install either engine.",
		image: "Docker image",
		imageHint: "Enter an image already available locally. Saving does not pull images or start containers.",
		bubblewrapHint: "Bubblewrap uses existing bwrap and Bash inside Linux or WSL, without a Docker image.",
		workspaceAccess: "Workspace access",
		access: { "read-write": "Read and write", "read-only": "Read only" },
		timeout: "Command timeout (seconds)",
		externalTools: "External tools",
		allowWeb: "Allow web search tools",
		allowWebHint:
			"Permits configured web tools to run outside the sandbox; this does not enable container networking.",
		hostMcp: "Allowed local MCP services",
		remoteMcp: "Allowed remote MCP services",
		mcpHint:
			"Enter configured service names separated by commas. This records an allowlist without starting or installing services.",
		save: "Save profile draft",
		default: "Default environment",
		defaultHint:
			"Records the environment intended for new tasks. The execution service must still check engine and image availability, without falling back to local execution.",
		local: "Local execution (no sandbox)",
		empty:
			"No isolated environments configured. Add a Docker or Bubblewrap profile to choose it as the default.",
		notChecked: "Profile draft · availability not checked",
		workspaceHint:
			"The task's project provides the workspace. Read-only access applies to that directory; external tools retain their own allowlists.",
		editNamed: "Edit {name}",
		removeNamed: "Delete {name}",
		remove: "Delete sandbox profile",
		removeHint:
			"Delete the frontend profile “{name}”? Its default selection will reset to local. Containers and images are unaffected.",
		errors: {
			name: "Start with a lowercase letter; use up to 48 lowercase letters, digits or hyphens. Names none, local and all are reserved.",
			duplicate: "A profile with this name already exists.",
			timeout: "Timeout must be an integer from 1 to 3600.",
			image: "Enter an image name without whitespace.",
			servers: "MCP names may contain only letters, digits, periods, underscores and hyphens.",
			missing: "The original profile no longer exists. Add a new one.",
			storage: "The draft is held in memory but could not be saved locally. Try again.",
		},
	},
};
