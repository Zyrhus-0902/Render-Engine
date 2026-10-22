# Style references

Put one image per look here (e.g. `day_clear.jpg`) and point a preset at it:

```yaml
style_reference: day_clear.jpg
style_strength: 0.3
```

The reference steers palette, light and mood through FLUX Redux. It also works
as the colour-harmonisation anchor (`harmonize.anchor: style_reference`).
Pick a photograph whose light you want every render in the set to share. Keep
`style_strength` low (0.2-0.4): higher values start to copy its content.
