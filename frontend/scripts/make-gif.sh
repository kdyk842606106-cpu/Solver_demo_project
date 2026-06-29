#!/bin/bash
cd "$(dirname "$0")/.."
node scripts/pngs-to-gif.js test-results/gif-frames test-results/demo.gif 1500
