import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape, Template

logger = logging.getLogger(__name__)


class TemplateRenderer:
    """
    Lightweight template renderer using Jinja2.

    Initialized once at application startup with the templates directory.
    Handles HTML template rendering with automatic HTML escaping for security.

    Supports both sync and async rendering:
    - Use render() for simple variable substitution (faster, most common)
    - Use render_async() if templates need to call async functions (rare)
    """

    def __init__(self, templates_dir: Path) -> None:
        """
        Initialize the Jinja2 environment.

        Args:
            templates_dir: Path to the directory containing email templates
        """
        self.templates_dir = templates_dir

        # create Jinja2 environment with HTML auto-escaping
        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(["html", "xml"]),
            # enable async for flexibility, but we'll mainly use sync rendering
            enable_async=True,
        )

        logger.info(
            "Template renderer initialized", extra={"templates_dir": str(templates_dir)}
        )

    def render(self, template_name: str, **variables) -> str:
        """
        Render a template synchronously with the provided variables.

        Use this for simple variable substitution in email templates.
        Fast and straightforward for most use cases.

        Args:
            template_name: Name of the template file (without .html extension)
            **variables: Variables to pass to the template

        Returns:
            Rendered HTML string

        Raises:
            jinja2.TemplateNotFound: If template doesn't exist
            jinja2.TemplateSyntaxError: If template has syntax errors
        """
        template: Template = self.env.get_template(f"{template_name}.html")
        return template.render(**variables)

    async def render_async(self, template_name: str, **variables) -> str:
        """
        Render a template asynchronously with the provided variables.

        Use this only if your template needs to call async functions/filters.
        For simple variable substitution, use render() instead (it's faster).

        Args:
            template_name: Name of the template file (without .html extension)
            **variables: Variables to pass to the template

        Returns:
            Rendered HTML string

        Raises:
            jinja2.TemplateNotFound: If template doesn't exist
            jinja2.TemplateSyntaxError: If template has syntax errors
        """
        template: Template = self.env.get_template(f"{template_name}.html")
        return await template.render_async(**variables)

    def health_check(self) -> bool:
        """
        Verify template renderer is functional.

        Returns:
            True if templates directory exists and is readable
        """
        return self.templates_dir.exists() and self.templates_dir.is_dir()
