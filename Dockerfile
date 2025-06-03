FROM python:3.11-slim

# ── System deps (cmake, g++, just) ────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        cmake \
        g++ \
        make \
        curl \
    && curl -fsSL https://just.systems/install.sh | bash -s -- --to /usr/local/bin \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Python deps ───────────────────────────────────────────────────────────────
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        streamlit \
        plotly \
        yfinance \
        pandas \
        numpy

# ── Copy source ───────────────────────────────────────────────────────────────
COPY core/       ./core/
COPY strategies/ ./strategies/
COPY scripts/    ./scripts/
COPY app.py      ./
COPY CMakeLists.txt ./
COPY Justfile    ./

# ── Build C++ core ────────────────────────────────────────────────────────────
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build build -j$(nproc)

# ── Runtime dirs ─────────────────────────────────────────────────────────────
RUN mkdir -p data results

EXPOSE 8501

# ── Entrypoint ────────────────────────────────────────────────────────────────
CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]
