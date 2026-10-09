################################################################################
#                                  __main__                                    #
#                                                                              #
# `python -m skforecast_ai` runs the CLI, as the `skforecast-ai` command does  #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from .cli import app

if __name__ == "__main__":
    app(prog_name="skforecast-ai")
