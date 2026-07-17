# Unit test cli config skforecast_ai

from typer.testing import CliRunner

from skforecast_ai.cli import app

runner = CliRunner()


class TestVersion:
    """Tests for the --version flag."""

    def test_version_prints_version(self):
        """
        --version prints the version string and exits.
        """
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "skforecast-ai" in result.output
        assert "0.2.0" in result.output


class TestConfigPath:
    """Tests for the config path command."""

    def test_config_path_prints_path(self):
        """
        Config path prints the config file location.
        """
        result = runner.invoke(app, ["config", "path"])
        assert result.exit_code == 0
        assert "skforecast-ai" in result.output
        assert "config.toml" in result.output


class TestConfigSet:
    """Tests for the config set command."""

    def test_config_set_creates_file(self, tmp_path, monkeypatch):
        """
        Config set creates the config file with the correct value.
        """
        config_dir = tmp_path / "skforecast-ai"
        config_file = config_dir / "config.toml"

        monkeypatch.setattr("skforecast_ai.config.CONFIG_DIR", config_dir)
        monkeypatch.setattr("skforecast_ai.config.CONFIG_FILE", config_file)
        monkeypatch.setattr("skforecast_ai.cli.CONFIG_FILE", config_file)

        result = runner.invoke(app, ["config", "set", "llm.provider", "ollama:llama3"])
        assert result.exit_code == 0
        assert "Set" in result.output
        assert config_file.exists()
        content = config_file.read_text()
        assert "ollama:llama3" in content

    def test_config_set_base_url(self, tmp_path, monkeypatch):
        """
        Config set stores base_url correctly.
        """
        config_dir = tmp_path / "skforecast-ai"
        config_file = config_dir / "config.toml"

        monkeypatch.setattr("skforecast_ai.config.CONFIG_DIR", config_dir)
        monkeypatch.setattr("skforecast_ai.config.CONFIG_FILE", config_file)
        monkeypatch.setattr("skforecast_ai.cli.CONFIG_FILE", config_file)

        result = runner.invoke(
            app, ["config", "set", "llm.base_url", "http://localhost:11434"]
        )
        assert result.exit_code == 0
        content = config_file.read_text()
        assert "http://localhost:11434" in content

    def test_config_set_boolean_value(self, tmp_path, monkeypatch):
        """
        Config set handles boolean values correctly.
        """
        config_dir = tmp_path / "skforecast-ai"
        config_file = config_dir / "config.toml"

        monkeypatch.setattr("skforecast_ai.config.CONFIG_DIR", config_dir)
        monkeypatch.setattr("skforecast_ai.config.CONFIG_FILE", config_file)
        monkeypatch.setattr("skforecast_ai.cli.CONFIG_FILE", config_file)

        result = runner.invoke(
            app, ["config", "set", "llm.send_data_to_llm", "true"]
        )
        assert result.exit_code == 0
        content = config_file.read_text()
        assert "send_data_to_llm = true" in content

    def test_config_set_invalid_key(self):
        """
        Config set rejects invalid keys with a helpful error.
        """
        result = runner.invoke(app, ["config", "set", "invalid.key", "value"])
        assert result.exit_code == 1
        assert "Unknown config key" in result.output

    def test_config_set_multiple_values(self, tmp_path, monkeypatch):
        """
        Config set accumulates multiple values in the same file.
        """
        config_dir = tmp_path / "skforecast-ai"
        config_file = config_dir / "config.toml"

        monkeypatch.setattr("skforecast_ai.config.CONFIG_DIR", config_dir)
        monkeypatch.setattr("skforecast_ai.config.CONFIG_FILE", config_file)
        monkeypatch.setattr("skforecast_ai.cli.CONFIG_FILE", config_file)

        runner.invoke(app, ["config", "set", "llm.provider", "openai:gpt-4o"])
        runner.invoke(
            app, ["config", "set", "llm.base_url", "http://localhost:11434"]
        )
        result = runner.invoke(app, ["config", "set", "output.format", "json"])
        assert result.exit_code == 0
        content = config_file.read_text()
        assert "openai:gpt-4o" in content
        assert "http://localhost:11434" in content
        assert "json" in content


class TestConfigShow:
    """Tests for the config show command."""

    def test_config_show_empty(self, tmp_path, monkeypatch):
        """
        Config show with no config file prints a dim message.
        """
        config_file = tmp_path / "nonexistent" / "config.toml"
        monkeypatch.setattr("skforecast_ai.config.CONFIG_FILE", config_file)
        monkeypatch.setattr("skforecast_ai.cli.CONFIG_FILE", config_file)

        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "No config file" in result.output

    def test_config_show_with_values(self, tmp_path, monkeypatch):
        """
        Config show displays stored values.
        """
        config_dir = tmp_path / "skforecast-ai"
        config_file = config_dir / "config.toml"

        monkeypatch.setattr("skforecast_ai.config.CONFIG_DIR", config_dir)
        monkeypatch.setattr("skforecast_ai.config.CONFIG_FILE", config_file)
        monkeypatch.setattr("skforecast_ai.cli.CONFIG_FILE", config_file)

        runner.invoke(app, ["config", "set", "llm.provider", "ollama:llama3"])
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "llm.provider" in result.output
        assert "ollama:llama3" in result.output


class TestConfigResolution:
    """Tests for the config resolution precedence chain."""

    def test_resolve_flag_over_env(self, monkeypatch):
        """
        CLI flag takes precedence over environment variable.
        """
        from skforecast_ai.cli import _resolve

        monkeypatch.setenv("SKFORECAST_AI_LLM", "env_value")
        result = _resolve("flag_value", "SKFORECAST_AI_LLM", "llm.provider")
        assert result == "flag_value"

    def test_resolve_env_over_config(self, tmp_path, monkeypatch):
        """
        Environment variable takes precedence over config file.
        """
        from skforecast_ai.cli import _resolve

        config_dir = tmp_path / "skforecast-ai"
        config_file = config_dir / "config.toml"
        config_dir.mkdir(parents=True)
        config_file.write_text('[llm]\nprovider = "config_value"\n')

        monkeypatch.setattr("skforecast_ai.config.CONFIG_FILE", config_file)
        monkeypatch.setenv("SKFORECAST_AI_LLM", "env_value")

        result = _resolve(None, "SKFORECAST_AI_LLM", "llm.provider")
        assert result == "env_value"

    def test_resolve_config_when_no_flag_or_env(self, tmp_path, monkeypatch):
        """
        Config file value used when no flag or env var is set.
        """
        from skforecast_ai.cli import _resolve

        config_dir = tmp_path / "skforecast-ai"
        config_file = config_dir / "config.toml"
        config_dir.mkdir(parents=True)
        config_file.write_text('[llm]\nprovider = "config_value"\n')

        monkeypatch.setattr("skforecast_ai.config.CONFIG_FILE", config_file)
        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)

        result = _resolve(None, "SKFORECAST_AI_LLM", "llm.provider")
        assert result == "config_value"

    def test_resolve_returns_none_when_nothing_set(self, tmp_path, monkeypatch):
        """
        Returns None when no flag, env var, or config value exists.
        """
        from skforecast_ai.cli import _resolve

        config_file = tmp_path / "nonexistent" / "config.toml"
        monkeypatch.setattr("skforecast_ai.config.CONFIG_FILE", config_file)
        monkeypatch.delenv("SKFORECAST_AI_LLM", raising=False)

        result = _resolve(None, "SKFORECAST_AI_LLM", "llm.provider")
        assert result is None
