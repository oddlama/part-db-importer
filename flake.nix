{
  inputs = {
    devshell = {
      url = "github:numtide/devshell";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    flake-parts.url = "github:hercules-ci/flake-parts";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    pre-commit-hooks = {
      url = "github:cachix/pre-commit-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs:
    inputs.flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [
        inputs.devshell.flakeModule
        inputs.pre-commit-hooks.flakeModule
        inputs.treefmt-nix.flakeModule
      ];

      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      perSystem =
        {
          config,
          pkgs,
          ...
        }:
        let
          pythonEnv = pkgs.python311.withPackages (
            ps: with ps; [
              playwright
              pyyaml
              tqdm
            ]
          );

          # Create a package that includes playwright browsers
          importer-with-browsers = pkgs.writeShellScriptBin "part-db-importer" ''
            export PLAYWRIGHT_BROWSERS_PATH=${pkgs.playwright-driver.browsers}
            export PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true
            export PLAYWRIGHT_HOST_PLATFORM_OVERRIDE="ubuntu-24.04"
            ${pythonEnv}/bin/python ${./importer.py} "$@"
          '';
        in
        {
          devshells.default = {
            packages = [
              config.treefmt.build.wrapper
              pythonEnv
              pkgs.playwright-driver.browsers
            ];

            env = [
              {
                name = "PLAYWRIGHT_BROWSERS_PATH";
                value = "${pkgs.playwright-driver.browsers}";
              }
              {
                name = "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS";
                value = true;
              }
              {
                name = "PLAYWRIGHT_HOST_PLATFORM_OVERRIDE";
                value = "ubuntu-24.04";
              }
            ];

            devshell.startup.pre-commit.text = config.pre-commit.installationScript;
          };

          pre-commit.settings.hooks.treefmt.enable = true;
          treefmt = {
            projectRootFile = "flake.nix";
            programs = {
              deadnix.enable = true;
              statix.enable = true;
              nixfmt.enable = true;
            };
          };

          packages.default = importer-with-browsers;
        };
    };
}
