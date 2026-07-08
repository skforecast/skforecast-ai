window.MathJax = {
  tex: {
    // 1. Add support for '$' and '$$' used by notebooks
    inlineMath: [["$", "$"], ["\\(", "\\)"]],
    displayMath: [["$$", "$$"], ["\\[", "\\]"]],
    processEscapes: true,
    processEnvironments: true
  },
  options: {
    // 2. We remove or comment out these lines so MathJax
    // searches for formulas across the ENTIRE page, not just in specific classes.
    // ignoreHtmlClass: ".*|",
    // processHtmlClass: "arithmatex"
  }
};