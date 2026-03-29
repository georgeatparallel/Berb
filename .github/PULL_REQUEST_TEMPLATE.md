# Pull Request Template

## 📋 Description

<!-- Describe the changes in this PR -->

**Type of Change:**
- [ ] ✨ New feature (non-breaking change which adds functionality)
- [ ] 🚀 Performance improvement
- [ ] 📚 Documentation update
- [ ] 🧪 Test additions
- [ ] 🐛 Bug fix
- [ ] ⚠️ Breaking change

## 🎯 Summary

<!-- Brief summary of what was implemented -->

## 📦 Enhancements Included

<!-- List enhancements included in this PR -->

### P0 Critical
- [ ] 

### P1 High
- [ ] 

### P2 Medium
- [ ] 

### P3 Low
- [ ] 

## 🧪 Testing

- [ ] Unit tests pass (`pytest tests/ -v`)
- [ ] Integration tests pass (`pytest tests/e2e/ -v`)
- [ ] Test coverage >= 75%
- [ ] No new warnings

**Test Results:**
```
Tests:     X passed, Y failed
Coverage:  Z%
```

## 📚 Documentation

- [ ] Code documentation (docstrings)
- [ ] API documentation
- [ ] User guide updated
- [ ] Migration guide created (if breaking changes)
- [ ] CHANGELOG updated

## 🔧 Configuration

<!-- List any new configuration options -->

```yaml
# Example config
```

## 📊 Impact Metrics

<!-- If applicable, show before/after metrics -->

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
|        |        |       |             |

## 🚀 Deployment Notes

- [ ] Database migrations required
- [ ] New environment variables
- [ ] New dependencies (see `requirements.txt`)
- [ ] Backward compatibility maintained

## 📝 Related Issues

<!-- Link related issues -->

Closes #

## 👥 Reviewers

Please review:
- [ ] Code quality and style
- [ ] Test coverage
- [ ] Documentation completeness
- [ ] Backward compatibility
- [ ] Performance impact

## 📸 Screenshots (if applicable)

<!-- Add screenshots if UI changes -->

## ✅ Checklist

- [ ] My code follows the project's style guidelines
- [ ] I have performed a self-review of my code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix/feature works
- [ ] New and existing tests pass locally
- [ ] Any dependent changes have been merged

---

## 📖 For Large PRs (v6 Complete)

**Note to Reviewers:** This is a large PR completing multiple enhancements. Please focus on:
1. Architecture consistency
2. Reasoning integration patterns
3. Test coverage adequacy
4. Documentation completeness

For detailed implementation details, see relevant `BERB_V6_*.md` documents.
