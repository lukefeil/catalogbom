# GitHub Wiki Sources

This folder stores the version-controlled landing page and navigation for the
Catalog BOM GitHub Wiki. It is not automatically published by pushing this main
repository. GitHub stores the native Wiki in a separate `catalogbom.wiki.git`
repository.

## Files

- [Home.md](Home.md): wiki home page.
- [_Sidebar.md](_Sidebar.md): shared wiki navigation.
- [_Footer.md](_Footer.md): shared wiki footer.

The wiki links to [the user guide](../docs/userguide.md) and
[the architecture](../docs/architecture.md) in the main repository instead of
duplicating them. Keep those canonical documents current alongside code changes.
Absolute GitHub links in the published pages work independently of this folder
and the wiki clone location. This README is maintainer guidance, not a wiki page
to publish.

## Initial Publishing

1. Enable Wikis in the GitHub repository settings if necessary.
2. Open the Wiki tab and create its first Home page through GitHub. GitHub requires
   an initial page before the wiki repository can be cloned.
3. From the main repository root, clone the separate wiki into a sibling folder:

```sh
git clone https://github.com/lukefeil/catalogbom.wiki.git ../catalogbom-wiki
```

4. Copy only the publishable pages, review them, commit, and push in that clone:

```sh
cp wiki/Home.md wiki/_Sidebar.md wiki/_Footer.md ../catalogbom-wiki/
git -C ../catalogbom-wiki diff
git -C ../catalogbom-wiki add Home.md _Sidebar.md _Footer.md
git -C ../catalogbom-wiki commit -m "Publish Catalog BOM wiki navigation"
git -C ../catalogbom-wiki push
```

The wiki clone needs its own Git author configuration and GitHub authentication
if those are not already available globally. Use its default branch; do not assume
it has the same branch name as the main repository.

## Later Updates

Pull the wiki clone before copying updated pages, then repeat the review, commit,
and push steps. Review conflicting online wiki edits rather than overwriting them
without checking. Keep source-page changes committed in the main repository too.
No wiki repository was created or published by adding this folder.

See [GitHub's wiki documentation](https://docs.github.com/en/communities/documenting-your-project-with-wikis/adding-or-editing-wiki-pages).