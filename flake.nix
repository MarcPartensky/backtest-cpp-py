{
  description = "Event-driven backtesting engine";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    uv2nix.url = "github:pyproject-nix/uv2nix";
    uv2nix.inputs.nixpkgs.follows = "nixpkgs";
    pyproject-nix.url = "github:pyproject-nix/pyproject.nix";
    pyproject-nix.inputs.nixpkgs.follows = "nixpkgs";
    pyproject-build-systems.url = "github:pyproject-nix/build-system-pkgs";
    pyproject-build-systems.inputs.pyproject-nix.follows = "pyproject-nix";
    pyproject-build-systems.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    uv2nix,
    pyproject-nix,
    pyproject-build-systems,
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      lib = nixpkgs.lib;
      python = pkgs.python312;

      workspace = uv2nix.lib.workspace.loadWorkspace {workspaceRoot = ./.;};
      overlay = workspace.mkPyprojectOverlay {sourcePreference = "wheel";};

      pythonSet = (pkgs.callPackage pyproject-nix.build.packages {inherit python;}).overrideScope (
        lib.composeManyExtensions [
          pyproject-build-systems.overlays.default
          overlay
        ]
      );

      venv = pythonSet.mkVirtualEnv "backtest-env" workspace.deps.default;
    in {
      packages.default = pkgs.stdenv.mkDerivation {
        pname = "backtest";
        version = "0.1.0";
        src = ./.;
        installPhase = ''
          mkdir -p $out/bin $out/lib
          cp -r . $out/lib/
          cat > $out/bin/backtest << EOF
          #!/bin/sh
          export PATH="${venv}/bin:\$PATH"
          cd $out/lib
          exec ${venv}/bin/streamlit run $out/lib/app.py \
            --browser.gatherUsageStats=false \
            --server.fileWatcherType=none \
            "\$@"
          EOF
          chmod +x $out/bin/backtest
        '';
      };

      devShells.default = pkgs.mkShell {
        packages = [pkgs.uv pkgs.just pkgs.ruff venv];
        shellHook = ''
          echo "backtest dev shell"
        '';
      };
      packages.default = pkgs.stdenv.mkDerivation {
        pname = "backtest";
        version = "0.1.0";
        src = ./.;
        
        nativeBuildInputs = [ pkgs.cmake pkgs.gcc ];
        buildInputs = [ venv ];
      
        buildPhase = ''
          cmake -B build -DCMAKE_BUILD_TYPE=Release
          cmake --build build -j$NIX_BUILD_CORES
        '';
      
        installPhase = ''
          mkdir -p $out/bin $out/lib
          cp -r . $out/lib/
          cp build/backtest $out/bin/backtest-cpp   # le binaire C++
          cat > $out/bin/backtest << EOF
          #!/bin/sh
          export PATH="${venv}/bin:\$PATH"
          cd $out/lib
          exec ${venv}/bin/streamlit run $out/lib/app.py \
            --browser.gatherUsageStats=false \
            --server.fileWatcherType=none \
            "\$@"
          EOF
          chmod +x $out/bin/backtest
        '';
      };
    });
}
