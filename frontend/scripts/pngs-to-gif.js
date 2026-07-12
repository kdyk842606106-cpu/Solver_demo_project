// scripts/pngs-to-gif.js
// Convert a sequence of PNG screenshots into an animated GIF

import fs from 'fs'
import path from 'path'
import { PNG } from 'pngjs'
import GIFEncoder from 'gif-encoder'

const FRAMES_DIR = process.argv[2] || './test-results/gif-frames'
const OUTPUT = process.argv[3] || './test-results/demo.gif'
const FRAME_DELAY = parseInt(process.argv[4], 10) || 1500 // ms per frame

async function main() {
  const files = fs.readdirSync(FRAMES_DIR)
    .filter(f => f.endsWith('.png'))
    .sort()

  if (files.length === 0) {
    console.error('No PNG files found in', FRAMES_DIR)
    process.exit(1)
  }

  console.log(`Found ${files.length} frames:`, files)

  // Read first image to get dimensions
  const firstPath = path.join(FRAMES_DIR, files[0])
  const firstBuf = fs.readFileSync(firstPath)
  const firstPng = PNG.sync.read(firstBuf)
  const width = firstPng.width
  const height = firstPng.height

  console.log(`Dimensions: ${width}x${height}`)

  // Create encoder with larger memory limit
  const encoder = new GIFEncoder(width, height, { highWaterMark: 1024 * 1024 * 10 })
  const stream = fs.createWriteStream(OUTPUT)
  encoder.pipe(stream)

  encoder.setRepeat(0) // loop forever
  encoder.setDelay(FRAME_DELAY)
  encoder.setQuality(15) // lower quality = smaller size

  encoder.writeHeader()

  for (const file of files) {
    const filePath = path.join(FRAMES_DIR, file)
    const buf = fs.readFileSync(filePath)
    const png = PNG.sync.read(buf)

    // Ensure dimensions match
    if (png.width !== width || png.height !== height) {
      console.warn(`Skipping ${file}: dimensions mismatch (${png.width}x${png.height} vs ${width}x${height})`)
      continue
    }

    encoder.addFrame(png.data)
    // Flush by reading to prevent memory limit
    while (encoder.read()) {}
    console.log(`Added frame: ${file}`)
  }

  encoder.finish()
  console.log(`GIF saved to: ${OUTPUT}`)

  // Wait for stream to finish
  await new Promise((resolve, reject) => {
    stream.on('finish', resolve)
    stream.on('error', reject)
  })
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
