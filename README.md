# WSL2 to Windows Godot LSP proxy

When using Neovim from WSL and Godot from Windows - the LSP file paths are not compatible

This is the simple TCP proxy that mirrors requests that LSP protocol does (JSON RPC), finds and replaces paths both ways: from linux to windows and from windows to linux

It works as a separate server that LSP Client from your editor should connect to


This project inspired by [godot-wsl-lsp](https://github.com/lucasecdb/godot-wsl-lsp) but basically does this proxying on a lower level and thanks to that it works very fast

