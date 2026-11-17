// Catalog checks that need no QML runtime.
const test = require("node:test")
const assert = require("node:assert/strict")
const fs = require("node:fs")
const path = require("node:path")

const root = path.join(__dirname, "..")
const catalogs = fs.readdirSync(path.join(root, "i18n")).filter((f) => f.endsWith(".json"))
const qml = fs.readdirSync(root).filter((f) => f.endsWith(".qml"))
  .map((f) => ({ file: f, text: fs.readFileSync(path.join(root, f), "utf8") }))

// Omarchy's Translations.t(key) treats "" as untranslated and returns the key
// itself, which is how "3時間unit.separator57分" reached the bar. A string that
// is empty in any language must be read as t(key, fallback).
test("strings that are empty in a catalog are read with a fallback", () => {
  const empty = new Set()
  for (const file of catalogs) {
    const catalog = JSON.parse(fs.readFileSync(path.join(root, "i18n", file), "utf8"))
    for (const [key, value] of Object.entries(catalog)) if (value === "") empty.add(key)
  }
  assert.ok(empty.has("unit.separator"), "ja.json joins duration units with an empty separator")
  for (const key of empty) {
    const call = new RegExp(`\\.t\\("${key.replace(/\./g, "\\.")}"\\s*([,)])`, "g")
    let uses = 0
    for (const { file, text } of qml) {
      for (const match of text.matchAll(call)) {
        uses++
        assert.equal(match[1], ",", `${file}: t("${key}") needs a fallback argument`)
      }
    }
    assert.ok(uses > 0, `"${key}" is empty in a catalog but never read`)
  }
})
