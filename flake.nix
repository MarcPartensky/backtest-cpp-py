{
  description = "Event-driven backtesting engine";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = nixpkgs.legacyPackages.${system};

      python = pkgs.python312;

      pythonEnv = python.withPackages (ps:
        with ps; [
          numpy
          pandas
          matplotlib
          yfinance
          # dev
          ruff
          streamlit
          plotly
        ]);
    in {
      devShells.default = pkgs.mkShell {
        packages = [
          pythonEnv
          pkgs.uv
          pkgs.just
          pkgs.ruff
        ];

        shellHook = ''
          echo "backtest dev shell — python $(python --version)"
        '';
      };
      packages.default = pkgs.stdenv.mkDerivation {
  pname = "backtest";
  version = "0.1.0";
  src = ./.;
  nativeBuildInputs = [ pkgs.makeWrapper ];
  buildInputs = [ pythonEnv ];
  installPhase = ''
    mkdir -p $out/bin $out/lib
    cp -r . $out/lib/
    cat > $out/bin/backtest << EOF
    #!/bin/sh
    export PATH="${pythonEnv}/bin:\$PATH"
    cd $out/lib
    exec ${pythonEnv}/bin/streamlit run $out/lib/app.py \
      --browser.gatherUsageStats=false \
      --server.fileWatcherType=none \
      "\$@"
    EOF
    chmod +x $out/bin/backtest
  '';
  };
    });
}
