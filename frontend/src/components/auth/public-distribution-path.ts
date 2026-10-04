/** The exact anonymous distribution protocol paths supported by the API. */
export function isPublicDistributionPath(pathname: string | null): boolean {
  return Boolean(
    pathname &&
    /^\/public\/(?:feed\.xml|feed\/(?:full|all|daily|weekly|monthly)\.xml|feed\/(?:full\/)?category\/[a-z-]+\.xml|items\/[a-zA-Z0-9-]+\.md|selected\.md|reports\/(?:daily|weekly|monthly)\/[a-zA-Z0-9-]+\.md|agent\.md|api\/(?:items(?:\/[a-zA-Z0-9-]+)?|hot|stories\/[a-zA-Z0-9-]+|reports\/(?:daily|weekly|monthly)\/[a-zA-Z0-9-]+)|mcp)$/.test(
      pathname,
    ),
  );
}
