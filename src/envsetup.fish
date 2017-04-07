# This fish script offers some convenience for working with ceph under fish
# shell. It's meant to be sourced.

## fish tweaks {{
# NOTE: reset various git prompt configurations to avoid performance penalty.
#
# Currently __fish_git_prompt invoking git command multiple times to get various
# information, which is super slow on large project like ceph, disable them for
# now.
#
set __fish_git_prompt_show_informative_status ''
set __fish_git_prompt_showdirtystate ''
# NOTE: this might not affect any performance
# set __fish_git_prompt_showstashstate ''
set __fish_git_prompt_showuntrackedfiles ''
set __fish_git_prompt_showupstream ''
# }}


## Environment and common utils
set -x TOP (realpath (dirname (status -f))/../)
set -x BUILD_ROOT $TOP/build
# NOTE: fish doesn't like non-existent directory in $PATH
if not test -d build
  echo "WARNING: not a working ceph tree. Abort."
  exit 1
end

set -x PATH $BUILD_ROOT/bin $PATH

function ctop -d 'cd back to top directory'
  cd $TOP
end

function croot -d 'cd back to build root (the most used one)'
  cd $BUILD_ROOT
end

## Useful command aliases
alias vstart $TOP/src/vstart.sh

## Drop to BUILD_ROOT
cd $BUILD_ROOT
