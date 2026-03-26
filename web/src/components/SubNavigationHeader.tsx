import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import MarketplaceLink from './MarketplaceLink.tsx'
import PageNav from './PageNav.tsx'


// Component

        function SubNavigationHeader({
            workLabel,
            schoolLabel,
            lifeLabel
        }: {
            workLabel: string;
            schoolLabel: string;
            lifeLabel: string;
        }) {
            return (
                <header className={"pageNav_pageNav__aX6Rg"}>
                    <div className={"pageNav_pageNavInner__VGHgv pageNav_fluid__myf1s"}>
                        <div>
                            <div className={"TemplateGallerySubNavigationWithCategories_left__3F_J_"}>
                                <MarketplaceLink />
                            </div>
                        </div>
                        <PageNav
                            workLabel={workLabel}
                            schoolLabel={schoolLabel}
                            lifeLabel={lifeLabel}
                        />
                    </div>
                </header>
            );
        }
    

export default SubNavigationHeader
