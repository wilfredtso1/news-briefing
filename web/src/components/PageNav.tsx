import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import CategoryNavLink from './CategoryNavLink.tsx'
import TemplateSearchInput from './TemplateSearchInput.tsx'
import SearchButton from './SearchButton.tsx'


// Component

        function PageNav({
            workLabel,
            schoolLabel,
            lifeLabel
        }: {
            workLabel: string;
            schoolLabel: string;
            lifeLabel: string;
        }) {
            return (
                <nav className={"pageNav_pageNavLinks__cz_AI"}>
                    <div className={"pageNav_pageNavMenu__B8fC0"}>
                        <NavItem variant="work" label={workLabel} />
                        <NavItem variant="school" label={schoolLabel} />
                        <NavItem variant="life" label={lifeLabel} />
                    </div>
                    <div className={"pageNav_pageNavCta__UDjNk"}>
    
                    </div>
                    <div className={"pageNav_pageNavRightContent__THuCA"}>
                        <form
                            role={"search"}
                            autoComplete={"off"}
                            autoCapitalize={"off"}
                            autoCorrect={"off"}
                            className={"templateGalleryHeroAutocomplete_form__or5jF templateGalleryHeroAutocomplete_formNav__y_FzL"}
                        >
                            <div className={"autocomplete_eventDelegationContainer___ZChF"}>
                                <div
                                    className={"input_root__sj8RO templateGalleryHeroAutocomplete_autocompleteRoot__Bpo0y input_sizeMedium__Y3knn input_hasAfter__zhGrc"}
                                    style={{ "--before-width": "0rem", "--after-width": "1.75rem" } as React.CSSProperties}
                                >
                                    <TemplateSearchInput />
                                    <span className={"input_after__MsoSh"}>
                                        <div role={"group"} className={"iconButton_group__KfvJp"}>
                                            <SearchButton />
                                        </div>
                                    </span>
                                </div>
                            </div>
                        </form>
                    </div>
                </nav>
            );
        }
    

// Subcomponents

        function NavItem({ variant, label }: { variant: string; label: string }) {
            return <CategoryNavLink variant={variant} label={label} />;
        }
    

export default PageNav
