# Terminal demo of the snipmd CLI. Render with: vhs demo/demo.tape
# Runs the real model, so it needs the MLX weights (snipmd pull) first.
# The pause after the second command is the model loading. The menu bar
# app and `snipmd serve` keep the model loaded, so they skip it.

Output demo/demo.gif

Set Shell "bash"
Set FontSize 15
Set Width 1200
Set Height 560
Set Padding 18
Set TypingSpeed 35ms
Set Theme "Catppuccin Latte"

Hide
Type "export PATH=$PWD/.venv/bin:$PATH SNIPMD_HOME=$(mktemp -d) PS1='$ '" Enter
Type "clear" Enter
Show

Type "snipmd doctor" Enter
Wait@30s /\$\s*$/
Sleep 2.5s

Type "snipmd demo/crop.png --mode latex" Enter
Wait@120s /\$\s*$/
Sleep 2.5s

Type "snipmd history" Enter
Wait@30s /\$\s*$/
Sleep 3s
