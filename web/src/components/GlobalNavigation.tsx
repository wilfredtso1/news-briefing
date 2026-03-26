import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Notion_logo_block from './icons/Notion_logo_block.tsx'
import Notion_logo from './icons/Notion_logo.tsx'
import NotionLogoLink from './NotionLogoLink.tsx'
import NavigationDropdownTrigger from './NavigationDropdownTrigger.tsx'
import ThemeWrapper from './ThemeWrapper.tsx'
import NavigationLink from './NavigationLink.tsx'
import PrimaryLinkButton from './PrimaryLinkButton.tsx'


// Component

        function GlobalNavigation() {
            return (
                <nav className={"globalNavigation_globalNavigation__7c1YP"}>
                    <div className={"globalNavigation_container__x43sE"}>
                        <div className={"globalNavigation_logoContainer__BR_e9"}>
                            <NotionLogoLink
                                className="globalNavigation_logo__i44_w"
                                logo={<Notion_logo_block />}
                            />
                        </div>
                        <div className={"globalNavigation_links__tZquA"}>
                            <NavDropdown id="product" label="Product" />
                            <NavDropdown id="ai" label="AI" />
                            <NavDropdown id="solutions" label="Solutions" />
                            <NavDropdown id="resources" label="Resources" />
                            <NavigationLink label="Enterprise" />
                            <NavigationLink label="Pricing" />
                            <NavigationLink label="Request a demo" />
                        </div>
                        <div className={"globalNavigation_actions__hEI1Y"}>
                            <span className={"globalNavigation_secondaryActions__5gLqb"}>
                                <div
                                    id={"g_id_onload"}
                                    style={{
                                        position: "absolute",
                                        top: "62px",
                                        insetInlineEnd: "18px",
                                        transform: "scale(0.9)",
                                        transformOrigin: "right top",
                                        zIndex: "100"
                                    }}
                                >
                                </div>
                                <NavigationLink label="Log in" />
                            </span>
                            <span className={"globalNavigation_primaryCta___fviu"}>
                                <PrimaryLinkButton label="Get Notion free" />
                            </span>
                            <div className={"globalNavigation_mobileActions__7AZdH sf-hidden"}>
                            </div>
                        </div>
                    </div>
                </nav>
            );
        }
    

// Subcomponents

        function NavDropdown({ id, label }: { id: string; label: string }) {
            return (
                <div id={id} className={"globalNavigation_dropdownContainer__8i441"}>
                    <NavigationDropdownTrigger label={label} />
                    <div className={"globalNavigation_dropdown__vn77x"}>
                        <ThemeWrapper />
                    </div>
                </div>
            );
        }
    

export default GlobalNavigation
