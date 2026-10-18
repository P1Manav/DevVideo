const { formatTag } = require("./util.js");

function runTagger() {
  console.log(formatTag("intro_scene", 0.0));
}

module.exports = { runTagger };
